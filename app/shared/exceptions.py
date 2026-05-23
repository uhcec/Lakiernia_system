class AppException(Exception):
    """Base application exception for reusable domain errors."""

    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class ResourceNotFoundError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=404)


class InvalidStatusTransitionError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=409)