from pydantic import BaseModel, ConfigDict, Field

HANGING_MAX_ACTIVE_ORDERS_LIMIT = 20


class ShopSettingsRead(BaseModel):
    hanging_max_active_orders: int


class ShopSettingsUpdate(BaseModel):
    hanging_max_active_orders: int = Field(ge=1, le=HANGING_MAX_ACTIVE_ORDERS_LIMIT)

    model_config = ConfigDict(extra="forbid")
