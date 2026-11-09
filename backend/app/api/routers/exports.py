from datetime import date

from fastapi import APIRouter, Response

from app.api.deps import Membership, SessionDep
from app.services.exporter import export_xlsx

router = APIRouter(prefix="/ledgers/{ledger_id}/export", tags=["export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("")
async def export(
    member: Membership,
    session: SessionDep,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    content = await export_xlsx(session, member.ledger_id, date_from, date_to)
    return Response(
        content,
        media_type=_XLSX,
        headers={"Content-Disposition": 'attachment; filename="walletly-export.xlsx"'},
    )
