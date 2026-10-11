from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    """Input schema: unknown fields are refused."""
    model_config = ConfigDict(extra="forbid")


class Quantiles(BaseModel):
    p10: float
    p50: float
    p90: float
