from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FoilCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    supplier: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FoilUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    supplier: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FoilRead(BaseModel):
    id: int
    name: str
    code: str
    supplier: str | None = None
    notes: str | None = None
    usage_count: int
    created_at: datetime
    updated_at: datetime


class FoilSummaryRead(BaseModel):
    """Compact foil view embedded in a work order read model."""

    id: int
    name: str
    code: str


class FoilListResponse(BaseModel):
    items: list[FoilRead]
    total: int
    limit: int
    offset: int
