from pydantic import BaseModel


class CeleryAppSettings(BaseModel):
    broker_url: str
    task_default_exchange: str | None = None
    task_default_queue: str | None = None
    event_exchange: str | None = None
    event_queue_prefix: str | None = None
    control_exchange: str | None = None
