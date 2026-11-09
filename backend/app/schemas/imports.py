from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportRowError(BaseModel):
    row: int  # номер строки в файле, как его видит пользователь
    message: str


class ImportResult(BaseModel):
    total_rows: int
    created: int
    skipped_duplicates: int
    errors: list[ImportRowError]
    dry_run: bool


class ImportBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    total_rows: int
    created: int
    skipped_duplicates: int
    errors: int
    created_at: datetime
