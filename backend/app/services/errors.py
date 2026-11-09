class DomainError(Exception):
    """Ошибка бизнес-логики. Сервис не знает про HTTP — код ответа выбирает слой API."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    pass


class PermissionDeniedError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class InvalidDataError(DomainError):
    pass


class TooBusyError(DomainError):
    """Сервер упёрся в лимит одновременных тяжёлых операций."""
