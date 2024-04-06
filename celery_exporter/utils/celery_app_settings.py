from pydantic import BaseModel


class CeleryAppSettings(BaseModel):
    broker_url: str
    event_exchange: str | None = None
    control_exchange: str | None = None
