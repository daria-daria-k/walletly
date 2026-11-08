from pydantic import BaseModel


class ImportRowError(BaseModel):
    row: int  # номер строки в файле, как его видит пользователь
    message: str


class ImportResult(BaseModel):
    total_rows: int
    created: int
    skipped_duplicates: int
    errors: list[ImportRowError]
    dry_run: bool
