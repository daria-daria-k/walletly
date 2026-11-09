import io
import time
import zipfile

import pytest
from openpyxl import Workbook

from app.core.limits import BusyLimiter
from app.services import file_parser, file_sandbox
from app.services.errors import InvalidDataError, TooBusyError

pytestmark = pytest.mark.anyio

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def _xlsx(replace: dict[str, bytes]) -> bytes:
    """Настоящий файл Excel, в котором заменены отдельные части архива."""
    book = Workbook()
    book.active.append(["Дата", "Сумма", "Счёт"])
    buffer = io.BytesIO()
    book.save(buffer)
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in (parts | replace).items():
            archive.writestr(name, data)
    return result.getvalue()


async def test_row_gap_does_not_hang_parser() -> None:
    sheet = (
        f'<?xml version="1.0"?><worksheet {NS}><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Дата</t></is></c></row>'
        '<row r="2000000000"><c r="A2000000000" t="inlineStr"><is><t>x</t></is></c></row>'
        "</sheetData></worksheet>"
    ).encode()
    started = time.monotonic()
    result = await file_sandbox.run("xlsx", _xlsx({"xl/worksheets/sheet1.xml": sheet}))
    assert result["rows"] == [[1, ["Дата"] + [None] * (file_parser.MAX_COLUMNS - 1)]]
    assert time.monotonic() - started < 15


async def test_huge_unpacked_size_is_rejected() -> None:
    bomb = _xlsx({"xl/sharedStrings.xml": b"A" * (file_parser.MAX_UNPACKED_BYTES + 1)})
    assert len(bomb) < 1024 * 1024  # проходит ограничение на размер загрузки
    with pytest.raises(InvalidDataError, match="после распаковки"):
        await file_sandbox.run("xlsx", bomb)


async def test_too_many_filled_rows_are_rejected() -> None:
    lines = "Дата;Сумма;Счёт\n" + "01.11.2026;1;Карта\n" * (file_parser.MAX_ROWS + 1)
    with pytest.raises(InvalidDataError, match="больше 5000 строк"):
        await file_sandbox.run("csv", lines.encode())


async def test_dates_cross_process_boundary_as_text() -> None:
    from datetime import datetime

    book = Workbook()
    book.active.append(["Дата"])
    book.active.append([datetime(2026, 11, 1, 12, 30)])
    buffer = io.BytesIO()
    book.save(buffer)
    rows = (await file_sandbox.run("xlsx", buffer.getvalue()))["rows"]
    assert rows[1][1][0] == "2026-11-01"


async def test_crash_in_parser_is_clean_error() -> None:
    with pytest.raises(InvalidDataError, match="Не удалось прочитать PDF"):
        await file_sandbox.run("pdf", b"not a pdf")


async def test_slow_parser_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_sandbox, "_TIMEOUT_SECONDS", 0.001)
    with pytest.raises(InvalidDataError, match="слишком много времени"):
        await file_sandbox.run("csv", b"a;b\n1;2\n")


def test_parser_does_not_receive_application_secrets() -> None:
    assert set(file_sandbox._CHILD_ENV) == {"PATH"}


async def test_limiter_answers_busy_instead_of_queueing_forever() -> None:
    limiter = BusyLimiter(1, 0.01, "занято")
    async with limiter.slot():
        with pytest.raises(TooBusyError, match="занято"):
            async with limiter.slot():
                pass
    async with limiter.slot():  # слот освободился
        pass


async def test_busy_server_answers_503(client, register, monkeypatch: pytest.MonkeyPatch) -> None:
    anna = await register()

    async def busy(kind: str, content: bytes) -> dict:
        raise TooBusyError("занято")

    monkeypatch.setattr(file_sandbox, "run", busy)
    response = await client.post(
        f"/api/ledgers/{anna.ledger_id}/import",
        files={"file": ("a.csv", b"x")},
        headers=anna.headers,
    )
    assert response.status_code == 503
