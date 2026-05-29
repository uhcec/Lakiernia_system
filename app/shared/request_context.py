from contextvars import ContextVar, Token
from uuid import uuid4


REQUEST_ID_HEADER = "X-Request-Id"
MAX_REQUEST_ID_LENGTH = 128

_current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


def generate_request_id() -> str:
    return uuid4().hex


def normalize_request_id(raw_request_id: str | None) -> str:
    if raw_request_id is None:
        return generate_request_id()

    request_id = raw_request_id.strip()
    if not request_id or len(request_id) > MAX_REQUEST_ID_LENGTH:
        return generate_request_id()

    if any(ord(character) < 33 or ord(character) > 126 for character in request_id):
        return generate_request_id()

    return request_id


def set_current_request_id(request_id: str) -> Token[str | None]:
    return _current_request_id.set(request_id)


def reset_current_request_id(token: Token[str | None]) -> None:
    _current_request_id.reset(token)


def get_current_request_id() -> str | None:
    return _current_request_id.get()
