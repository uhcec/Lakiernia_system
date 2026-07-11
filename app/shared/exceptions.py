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


class InvalidProcessStageTransitionError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=409)


class InvalidManagerPlanningError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=409)


class InvalidWorkOrderDataError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=422)


class InvalidPaintInventoryError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=409)


class InvalidAttachmentError(AppException):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail=detail, status_code=status_code)


class InvalidStationIdentityError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=400)


class DocumentGenerationUnavailableError(AppException):
    """CHANGES #17: the QC card's Excel-COM → PDF conversion needs a Windows host with Excel
    (owner decisions D1/D6, 2026-07-11). On a host without it (e.g. the Linux dev VPS) the
    endpoint must answer with a controlled Polish 503, not a raw 500."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=503)


class StationActionForbiddenError(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(detail=detail, status_code=403)
