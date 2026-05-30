from dataclasses import dataclass
from typing import Annotated

from fastapi import Header

from app.shared.enums import StationId
from app.shared.exceptions import InvalidStationIdentityError, StationActionForbiddenError


@dataclass(frozen=True)
class StationContext:
    station_id: StationId


def parse_station_id(raw_station_id: str | None) -> StationId:
    if raw_station_id is None or not raw_station_id.strip():
        return StationId.UNKNOWN

    normalized_station_id = raw_station_id.strip().upper().replace("-", "_")
    try:
        return StationId(normalized_station_id)
    except ValueError as exc:
        raise InvalidStationIdentityError(f"Invalid station identity: {raw_station_id}.") from exc


def get_station_context(
    x_station_id: Annotated[str | None, Header(alias="X-Station-Id")] = None,
) -> StationContext:
    return StationContext(station_id=parse_station_id(x_station_id))


def ensure_station_allowed(
    station_context: StationContext | None,
    *,
    allowed_station_ids: set[StationId],
    action: str,
) -> None:
    if station_context is None or station_context.station_id in {StationId.SYSTEM, StationId.UNKNOWN}:
        return

    if station_context.station_id not in allowed_station_ids:
        allowed_values = ", ".join(sorted(station_id.value for station_id in allowed_station_ids))
        raise StationActionForbiddenError(
            f"Station {station_context.station_id.value} is not allowed to perform {action}. Allowed stations: {allowed_values}."
        )