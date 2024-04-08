from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    GENERIC_HOSTNAME_TASK_SENT_METRIC: bool = Field(
        default=True,
        description=(
            'The metric celery_task_sent_total will be labeled with a generic hostname. '
            'This option helps with label cardinality when using a dynamic number of clients '
            "which create tasks. The default behavior is to label the metric with the generic hostname. "
            'Knowing which client sent a task might not be useful for many use cases as for example in '
            "Kubernetes environments where the client's hostname is a random string."
        ),
    )

    # PURGE_OFFLINE_WORKER_METRICS_AFTER_SECONDS must be greater or equal than WORKER_TIMEOUT_SECONDS
    PURGE_OFFLINE_WORKER_METRICS_AFTER_SECONDS: int = Field(
        default=10 * 60,
        description=(
            'If no heartbeat has been received from a worker in this many seconds, '
            'that a worker will be considered dead. Metrics will be purged for this worker after this many seconds.'
        ),
    )

    WORKER_TIMEOUT_SECONDS: int = Field(
        default=30,
        description=(
            'If no heartbeat has been received from a worker in this many seconds, '
            'that a worker will be considered dead.'
        ),
    )

    POSTFIX_EVENT_EXCHANGE: str = 'celeryev.topic'

    BROKER_URL: str = 'amqp://guest:guest@localhost:8672'

    PORT: int = Field(default=9808, description='The port the exporter will listen on')

    COLLECT_WORKER_METRICS_RETRY_INTERVAL: int = Field(
        default=1,
        description='Broker exception retry interval in seconds, default is 0 for immediately',
    )

    COLLECT_WORKER_PING_RETRY_INTERVAL: int = Field(default=60, description='Interval in seconds')

    COLLECT_WORKER_TIMEOUT_METRICS_INTERVAL: int = Field(default=15, description='Interval in seconds')

    COLLECT_QUEUE_METRICS_INTERVAL: int = Field(default=30, description='Interval in seconds')

    TRACK_WORKER_PING_TIMEOUT: int = Field(default=5, description='Timeout in seconds')

    LOG_LEVEL: str = 'INFO'

    PROMETHEUS_CLIENT_DISABLE_CREATED_METRICS: bool = True

    @model_validator(mode='after')
    def validate_timeout(self) -> 'Settings':
        if self.PURGE_OFFLINE_WORKER_METRICS_AFTER_SECONDS < self.WORKER_TIMEOUT_SECONDS:
            raise ValueError(
                'PURGE_OFFLINE_WORKER_METRICS_AFTER_SECONDS must be greater or equal than WORKER_TIMEOUT_SECONDS',
            )
        return self

    @model_validator(mode='after')
    def validate_collect_worker_metrics_retry_interval(self) -> 'Settings':
        if self.COLLECT_WORKER_METRICS_RETRY_INTERVAL < 0:
            raise ValueError(
                'COLLECT_WORKER_METRICS_RETRY_INTERVAL must be greater or equal than 0.',
            )
        return self

    @model_validator(mode='after')
    def validate_collect_worker_timeout_metrics_interval(self) -> 'Settings':
        if self.COLLECT_WORKER_TIMEOUT_METRICS_INTERVAL < 15:
            raise ValueError(
                'COLLECT_WORKER_TIMEOUT_METRICS_INTERVAL must be greater or equal than 15.',
            )
        return self

    @model_validator(mode='after')
    def validate_collect_queue_metrics_interval(self) -> 'Settings':
        if self.COLLECT_QUEUE_METRICS_INTERVAL < 30:
            raise ValueError(
                'COLLECT_QUEUE_METRICS_INTERVAL must be greater or equal than 30.',
            )
        return self

    @model_validator(mode='after')
    def validate_collect_worker_ping_retry_interval(self) -> 'Settings':
        if self.COLLECT_WORKER_PING_RETRY_INTERVAL < 15:
            raise ValueError(
                'COLLECT_WORKER_PING_RETRY_INTERVAL must be greater or equal than 15.',
            )
        return self

    @model_validator(mode='after')
    def validate_track_worker_ping_timeout(self) -> 'Settings':
        if self.TRACK_WORKER_PING_TIMEOUT < 5:
            raise ValueError(
                'TRACK_WORKER_PING_TIMEOUT must be greater or equal than 5.',
            )
        return self

    class Config:  # noqa: WPS431
        case_sensitive = True


settings = Settings()
