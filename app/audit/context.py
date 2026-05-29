from dataclasses import dataclass
from typing import Annotated

from fastapi import Header

from app.shared.enums import StationId
from app.shared.exceptions import InvalidStationIdentityError


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