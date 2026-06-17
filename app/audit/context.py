from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.shared.enums import StationId
from app.shared.exceptions import InvalidStationIdentityError, StationActionForbiddenError


@dataclass(frozen=True)
class StationContext:
    """Authorization context derived from the authenticated user (NA1).

    ``station_id`` and ``is_admin`` come from the JWT-authenticated user, never from a
    client-supplied header. ``None`` (passed by internal/seed callers) is treated as the trusted
    ``SYSTEM`` identity.
    """

    station_id: StationId
    is_admin: bool = False
    # Authenticated user id, recorded into the analytics stage-transition log. NULL today
    # (stations share an identity); populates automatically once operators get personal login.
    user_id: int | None = None


def parse_station_id(raw_station_id: str | None) -> StationId:
    if raw_station_id is None or not raw_station_id.strip():
        return StationId.UNKNOWN

    normalized_station_id = raw_station_id.strip().upper().replace("-", "_")
    try:
        return StationId(normalized_station_id)
    except ValueError as exc:
        raise InvalidStationIdentityError(f"Invalid station identity: {raw_station_id}.") from exc


def get_station_context(
    user: Annotated[User, Depends(get_current_user)],
) -> StationContext:
    return StationContext(
        station_id=parse_station_id(user.station_id),
        is_admin=bool(user.is_admin),
        user_id=user.id,
    )


def ensure_station_allowed(
    station_context: StationContext | None,
    *,
    allowed_station_ids: set[StationId],
    action: str,
) -> None:
    # ``None`` is the trusted internal/seed identity (SYSTEM). Authenticated requests always carry a
    # real station context; the missing-header (UNKNOWN) bypass is intentionally gone (NA1).
    if station_context is None or station_context.station_id == StationId.SYSTEM:
        return

    if station_context.is_admin:
        return

    if station_context.station_id not in allowed_station_ids:
        allowed_values = ", ".join(sorted(station_id.value for station_id in allowed_station_ids))
        raise StationActionForbiddenError(
            f"Station {station_context.station_id.value} is not allowed to perform {action}. Allowed stations: {allowed_values}."
        )