from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api.deps import Membership, SessionDep
from app.schemas.imports import ImportBatchRead, ImportResult
from app.services.importer import MAX_FILE_SIZE, import_history, import_transactions

router = APIRouter(prefix="/ledgers/{ledger_id}/import", tags=["import"])


@router.post("")
async def upload(
    file: UploadFile, member: Membership, session: SessionDep, dry_run: bool = False
) -> ImportResult:
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нужен файл .xlsx или .csv")
    # Читаем на байт больше лимита: так узнаём о превышении, не загружая весь файл
    content = await file.read(MAX_FILE_SIZE + 1)
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
    return await import_transactions(session, member, content, filename, dry_run=dry_run)


@router.get("/history")
async def history(member: Membership, session: SessionDep) -> list[ImportBatchRead]:
    return [
        ImportBatchRead.model_validate(batch)
        for batch in await import_history(session, member.ledger_id)
    ]
