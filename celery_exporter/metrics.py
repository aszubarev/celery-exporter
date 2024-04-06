from celery_exporter.conf import settings
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, disable_created_metrics

if settings.PROMETHEUS_CLIENT_DISABLE_CREATED_METRICS:
    disable_created_metrics()

BUCKETS = (                                                     # noqa: WPS317
    .005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0,          # noqa: WPS304
    2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0,
    50.0, 60.0, 70.0, 80.0, 90.0, 100.0,
)


registry = CollectorRegistry(auto_describe=True)

events_state_counters = {
    'task-sent': Counter(
        'celery_task_sent',
        'Sent when a task message is published.',
        ['name', 'hostname', 'service_name'],
        registry=registry,
    ),
    'task-received': Counter(
        'celery_task_received',
        'Sent when the worker receives a task.',
        ['name', 'hostname', 'service_name'],
        registry=registry,
    ),
    'task-started': Counter(
        'celery_task_started',
        'Sent just before the worker executes the task.',
        ['name', 'hostname', 'service_name'],
        registry=registry,
    ),
    'task-succeeded': Counter(
        'celery_task_succeeded',
        'Sent if the task executed successfully.',
        ['name', 'hostname', 'service_name'],
        registry=registry,
    ),
    'task-failed': Counter(
        'celery_task_failed',
        'Sent if the execution of the task failed.',
        ['name', 'hostname', 'exception', 'service_name'],
        registry=registry,
    ),
    'task-rejected': Counter(
        'celery_task_rejected',
        'The task was rejected by the worker, possibly to be re-queued or moved to a dead letter queue.',
        ['name', 'hostname', 'service_name'],
        registry=registry,
    ),
    'task-revoked': Counter(
        'celery_task_revoked',
        'Sent if the task has been revoked.',
        ['name', 'hostname', 'service_name'],
        registry=registry,
    ),
    'task-retried': Counter(
        'celery_task_retried',
        'Sent if the task failed, but will be retried in the future.',
        ['name', 'hostname', 'service_name'],
        registry=registry,
    ),
}

celery_worker_up = Gauge(
    'celery_worker_up',
    'Indicates if a worker has recently sent a heartbeat.',
    ['hostname', 'service_name'],
    registry=registry,
)
worker_tasks_active = Gauge(
    'celery_worker_tasks_active',
    'The number of tasks the worker is currently processing',
    ['hostname', 'service_name'],
    registry=registry,
)
celery_task_runtime = Histogram(
    'celery_task_runtime',
    'Histogram of task runtime measurements.',
    ['name', 'hostname', 'service_name'],
    registry=registry,
    buckets=BUCKETS,
)
celery_queue_length = Gauge(
    'celery_queue_length',
    'The number of message in broker queue.',
    ['queue_name', 'service_name'],
    registry=registry,
)
celery_active_consumer_count = Gauge(
    'celery_active_consumer_count',
    'The number of active consumer in broker queue.',
    ['queue_name', 'service_name'],
    registry=registry,
)
celery_active_worker_count = Gauge(
    'celery_active_worker_count',
    'The number of active workers in broker queue.',
    ['queue_name', 'service_name'],
    registry=registry,
)
celery_active_process_count = Gauge(
    'celery_active_process_count',
    'The number of active processes in broker queue.',
    ['queue_name', 'service_name'],
    registry=registry,
)
