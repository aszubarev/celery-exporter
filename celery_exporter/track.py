import datetime
import re
from collections import defaultdict
from typing import Any, Callable, TypeVar

import structlog
from amqp import ChannelError
from amqp.protocol import queue_declare_ok_t
from celery import Celery
from celery.app.control import Inspect
from celery.events.state import Task, Worker
from celery_exporter import metrics, state
from celery_exporter.conf import settings
from celery_exporter.utils.timezone import localtime
from kombu.connection import Connection

logger = structlog.get_logger()

EventType = TypeVar('EventType', bound=dict[str, Any])


def receive_event(func: Callable[[EventType, str], None]) -> Callable[[EventType, str], None]:

    def wrapper(event: EventType, service_name: str) -> None:
        # put event to celery.events.state.State
        (obj, _), _ = state.events_state.event(event)

        contextvars = {
            'event_type': event['type'],
            'service_name': service_name,
            'worker': getattr(obj, 'hostname', 'unknown'),
        }

        if isinstance(obj, Task):
            contextvars['task_uuid'] = obj.uuid
            contextvars['task_name'] = obj.name
            contextvars['task_state'] = obj.state

        with structlog.contextvars.bound_contextvars(**contextvars):
            logger.debug('Received event')
            func(event, service_name)

    return wrapper


@receive_event
def track_task_event(event: EventType, service_name: str) -> None:      # noqa: C901,WPS231
    task: Task = state.events_state.tasks.get(event['uuid'])

    worker_name = task.hostname
    if event['type'] == 'task-sent' and settings.GENERIC_HOSTNAME_TASK_SENT_METRIC:
        worker_name = 'generic'

    labels = {'task': task.name, 'worker': worker_name, 'service_name': service_name}
    if event['type'] == 'task-failed':
        labels['exception'] = _get_exception_class_name(task.exception)

    counter = metrics.events_state_counters.get(event['type'])
    if counter:
        counter.labels(**labels).inc()
        # noinspection PyProtectedMember
        logger.debug('Increment counter', metric_name=counter._name, labels=labels)
    else:
        logger.warning("Can't get counter")

    if event['type'] == 'task-succeeded':
        metrics.celery_task_runtime.labels(**labels).observe(task.runtime)
        # noinspection PyProtectedMember
        logger.debug('Observe', metric_name=metrics.celery_task_runtime._name, task_runtime=task.runtime)


@receive_event
def track_worker_heartbeat(event: EventType, service_name: str) -> None:
    worker_name = event['hostname']

    state.worker_last_seen[(worker_name, service_name)] = event['timestamp']

    worker: Worker = state.events_state.event(event)[0][0]

    active = worker.active or 0
    up = 1 if worker.alive else 0

    metrics.celery_worker_up.labels(worker=worker_name, service_name=service_name).set(up)
    metrics.celery_worker_tasks_active.labels(worker=worker_name, service_name=service_name).set(active)

    # noinspection PyProtectedMember
    logger.debug('Update gauge', metric_name=metrics.celery_worker_up._name, value=up)
    # noinspection PyProtectedMember
    logger.debug('Update gauge', metric_name=metrics.celery_worker_tasks_active._name, value=active)


@receive_event
def track_worker_status(event: EventType, service_name: str) -> None:
    is_online = event['type'] == 'worker-online'
    value = 1 if is_online else 0

    worker_name = event['hostname']

    metrics.celery_worker_up.labels(worker=worker_name, service_name=service_name).set(value)
    # noinspection PyProtectedMember
    logger.debug('Update gauge', metric_name=metrics.celery_worker_up._name, value=value)

    if event['type'] == 'worker-online':
        state.worker_last_seen[(worker_name, service_name)] = event['timestamp']
    else:
        _reset_worker_metrics(worker_name, service_name)


def track_worker_timeout() -> None:
    current_time = localtime().timestamp()
    # Make a copy of the last seen dict, so we can delete from the dict with no issues
    worker_last_seen_copy = state.worker_last_seen.copy()

    for worker_name, service_name in worker_last_seen_copy.keys():
        since = current_time - worker_last_seen_copy[(worker_name, service_name)]
        if since > settings.WORKER_TIMEOUT_SECONDS:
            logger.info('Worker timeout. Resetting metrics', worker=worker_name, service_name=service_name, since=since)

            _reset_worker_metrics(worker_name, service_name)

        if since > settings.PURGE_OFFLINE_WORKER_METRICS_AFTER_SECONDS:
            logger.info('Worker timeout. Purging metrics', worker=worker_name, service_name=service_name, since=since)

            _purge_worker_metrics(worker_name, service_name)


def track_worker_ping(app: Celery, service_name: str) -> None:
    logger.info('ping', service_name=service_name)

    pong = app.control.ping(timeout=settings.TRACK_WORKER_PING_TIMEOUT)

    for workers in pong:
        for worker_name in workers:
            logger.info('pong', worker=worker_name, service_name=service_name)

            state.worker_last_seen[(worker_name, service_name)] = datetime.datetime.utcnow().timestamp()

            metrics.celery_worker_up.labels(worker=worker_name, service_name=service_name).set(1)
            # noinspection PyProtectedMember
            logger.debug(
                'Update gauge',
                worker=worker_name,
                service_name=service_name,
                metric_name=metrics.celery_worker_up._name,
                value=1,
            )


def track_queue_metrics(app: Celery, connection: Connection, service_name: str) -> None:    # noqa: C901,WPS210,WPS231
    transport = connection.info()['transport']

    if transport not in {'redis', 'rediss', 'amqp', 'amqps', 'memory', 'sentinel'}:
        logger.warning('Queue length tracking is not available', transport=transport)

    inspect: Inspect = app.control.inspect()

    concurrency_per_worker = {
        worker: len(stats['pool'].get('processes', []))
        for worker, stats in (inspect.stats() or {}).items()
    }
    processes_per_queue: dict[str, int] = defaultdict(int)
    workers_per_queue: dict[str, int] = defaultdict(int)

    # request workers to response active queues
    # we need to cache queue info in exporter in case all workers are offline
    # so that no worker response to exporter will make active_queues return None
    queues = inspect.active_queues() or {}

    for worker, info_list in queues.items():
        for queue_info in info_list:
            queue_name = queue_info['name']

            state.queues[service_name].add(queue_name)

            workers_per_queue[queue_name] += 1
            processes_per_queue[queue_name] += concurrency_per_worker.get(worker, 0)

    for queue in state.queues[service_name]:
        metrics.celery_active_process_count.labels(
            queue_name=queue,
            service_name=service_name,
        ).set(processes_per_queue[queue])

        metrics.celery_active_worker_count.labels(
            queue_name=queue,
            service_name=service_name,
        ).set(workers_per_queue[queue])

        if transport in {'amqp', 'amqps', 'memory'}:
            rabbitmq_queue_info = _rabbitmq_queue_info(connection, queue)
            consumer_count = 0
            message_count = 0
            if rabbitmq_queue_info:
                consumer_count = rabbitmq_queue_info.consumer_count
                message_count = rabbitmq_queue_info.message_count

            metrics.celery_active_consumer_count.labels(
                queue_name=queue,
                service_name=service_name,
            ).set(consumer_count)

            metrics.celery_queue_length.labels(
                queue_name=queue,
                service_name=service_name,
            ).set(message_count)

        if transport in {'redis', 'rediss', 'sentinel'}:
            message_count = _redis_queue_length(connection, queue)
            metrics.celery_queue_length.labels(
                queue_name=queue,
                service_name=service_name,
            ).set(message_count)


def _reset_worker_metrics(worker_name: str, service_name: str) -> None:
    if (worker_name, service_name) not in state.worker_last_seen:
        return

    metrics.celery_worker_up.labels(worker=worker_name, service_name=service_name).set(0)
    metrics.celery_worker_tasks_active.labels(worker=worker_name, service_name=service_name).set(0)
    # noinspection PyProtectedMember
    logger.debug(
        'Update gauge',
        worker=worker_name,
        service_name=service_name,
        metric_name=metrics.celery_worker_up._name,
        value=0,
    )
    # noinspection PyProtectedMember
    logger.debug(
        'Update gauge',
        worker=worker_name,
        service_name=service_name,
        metric_name=metrics.celery_worker_tasks_active._name,
        value=0,
    )


def _purge_worker_metrics(worker_name: str, service_name: str) -> None:                         # noqa: C901,WPS231
    # Prometheus stores a copy of the metrics in memory, so we need to remove them
    # The key of the metrics is a string sequence e.g ('celery(queue_name)', 'host-1(hostname)')
    # noinspection PyProtectedMember
    for label_seq in list(metrics.celery_worker_tasks_active._metrics.keys()):
        if worker_name in label_seq and service_name in label_seq:
            metrics.celery_worker_tasks_active.remove(*label_seq)

    # noinspection PyProtectedMember
    for label_seq in list(metrics.celery_worker_up._metrics.keys()):                            # noqa: WPS440
        if worker_name in label_seq and service_name in label_seq:
            metrics.celery_worker_up.remove(*label_seq)

    for counter in metrics.events_state_counters.values():
        # noinspection PyProtectedMember
        for label_seq in list(counter._metrics.keys()):                                         # noqa: WPS440
            if worker_name in label_seq and service_name in label_seq:
                counter.remove(*label_seq)

    # noinspection PyProtectedMember
    for label_seq in list(metrics.celery_task_runtime._metrics.keys()):                         # noqa: WPS440
        if worker_name in label_seq and service_name in label_seq:
            metrics.celery_task_runtime.remove(*label_seq)

    del state.worker_last_seen[(worker_name, service_name)]                                     # noqa: WPS420


_exception_pattern = re.compile(r'^(\w+)\(')


def _get_exception_class_name(exception_name: str) -> str:
    match = _exception_pattern.match(exception_name)
    if match:
        return match.group(1)
    return 'UnknownException'


def _redis_queue_length(connection: Connection, queue: str) -> int:
    return connection.channel().client.llen(queue)


def _rabbitmq_queue_info(connection: Connection, queue: str) -> queue_declare_ok_t | None:
    try:
        return connection.default_channel.queue_declare(queue=queue, passive=True)
    except ChannelError as ex:
        if 'NOT_FOUND' in ex.message:
            logger.debug('Queue not found', queue=queue)
            return None
        raise ex
