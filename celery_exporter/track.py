import datetime
import re
from collections import defaultdict
from typing import Any, Callable, TypeVar

import structlog
from amqp import ChannelError
from amqp.protocol import queue_declare_ok_t
from celery import Celery
from celery.events.state import Task, Worker
from celery.utils import nodesplit
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
            'hostname': getattr(obj, 'hostname', 'unknown'),
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

    hostname = _get_hostname(task.hostname)
    if event['type'] == 'task-sent' and settings.GENERIC_HOSTNAME_TASK_SENT_METRIC:
        hostname = 'generic'

    labels = {'name': task.name, 'hostname': hostname, 'service_name': service_name}
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
    hostname = _get_hostname(event['hostname'])

    state.worker_last_seen[(hostname, service_name)] = event['timestamp']

    worker_state: Worker = state.events_state.event(event)[0][0]

    active = worker_state.active or 0
    up = 1 if worker_state.alive else 0

    metrics.celery_worker_up.labels(hostname=hostname, service_name=service_name).set(up)
    metrics.celery_worker_tasks_active.labels(hostname=hostname, service_name=service_name).set(active)

    # noinspection PyProtectedMember
    logger.debug('Update gauge', metric_name=metrics.celery_worker_up._name, value=up)
    # noinspection PyProtectedMember
    logger.debug('Update gauge', metric_name=metrics.celery_worker_tasks_active._name, value=active)


@receive_event
def track_worker_status(event: EventType, service_name: str) -> None:
    is_online = event['type'] == 'worker-online'
    value = 1 if is_online else 0

    hostname = _get_hostname(event['hostname'])

    metrics.celery_worker_up.labels(hostname=hostname, service_name=service_name).set(value)
    # noinspection PyProtectedMember
    logger.debug('Update gauge', metric_name=metrics.celery_worker_up._name, value=value)

    if event['type'] == 'worker-online':
        state.worker_last_seen[(hostname, service_name)] = event['timestamp']
    else:
        _forget_worker(hostname, service_name)


def track_timed_out_workers() -> None:
    now = localtime().timestamp()
    # Make a copy of the last seen dict, so we can delete from the dict with no issues
    worker_last_seen_copy = state.worker_last_seen.copy()

    for hostname, service_name in worker_last_seen_copy.keys():
        since = now - worker_last_seen_copy[(hostname, service_name)]
        if since > settings.WORKER_TIMEOUT_SECONDS:
            logger.info(
                'Have not seen %s for %s seconds. Removing from metrics',
                hostname,
                since,
            )
            _forget_worker(hostname, service_name)

        if since > settings.PURGE_OFFLINE_WORKER_METRICS_AFTER_SECONDS:
            logger.info(
                'Have not seen %s for %s seconds. Purging worker metrics',
                hostname,
                since,
            )
            _purge_worker_metrics(hostname, service_name)


def track_worker_ping(app: Celery, service_name: str) -> None:
    logger.info('ping %s', service_name)
    workers = app.control.ping(timeout=settings.TRACK_WORKER_PING_TIMEOUT)
    for worker in workers:
        for hostname in worker:
            logger.info('pong %s hostname: %s', service_name, hostname)

            state.worker_last_seen[(hostname, service_name)] = datetime.datetime.utcnow().timestamp()

            metrics.celery_worker_up.labels(hostname=hostname, service_name=service_name).set(1)
            # noinspection PyProtectedMember
            logger.debug('Updated gauge=%s value=%s', metrics.celery_worker_up._name, 1)


def track_queue_metrics(                                                                    # noqa: C901,WPS210
    app: Celery,
    connection: Connection,
    queue_cache: set[str],
    service_name: str,
) -> None:
    transport = connection.info()['transport']
    acceptable_transports = [
        'redis',
        'rediss',
        'amqp',
        'amqps',
        'memory',
        'sentinel',
    ]
    if transport not in acceptable_transports:
        logger.debug(
            'Queue length tracking is only implemented for %s',
            acceptable_transports,
        )
        return
    inspect = app.control.inspect()

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
            name = queue_info['name']
            queue_cache.add(name)
            workers_per_queue[name] += 1
            processes_per_queue[name] += concurrency_per_worker.get(worker, 0)

    for queue in queue_cache:
        if transport in ['amqp', 'amqps', 'memory']:                                        # noqa: WPS510
            consumer_count = _rabbitmq_queue_consumer_count(connection, queue)
            metrics.celery_active_consumer_count.labels(queue_name=queue, service_name=service_name).set(
                consumer_count,
            )

        metrics.celery_active_process_count.labels(queue_name=queue, service_name=service_name).set(
            processes_per_queue[queue],
        )
        metrics.celery_active_worker_count.labels(queue_name=queue, service_name=service_name).set(
            workers_per_queue[queue],
        )
        length = _queue_length(transport, connection, queue)
        if length is not None:
            metrics.celery_queue_length.labels(queue_name=queue, service_name=service_name).set(length)


def _forget_worker(hostname: str, service_name: str) -> None:
    if (hostname, service_name) in state.worker_last_seen:
        metrics.celery_worker_up.labels(hostname=hostname, service_name=service_name).set(0)
        metrics.celery_worker_tasks_active.labels(hostname=hostname, service_name=service_name).set(0)
        # noinspection PyProtectedMember
        logger.debug(
            'Updated gauge=%s value=%s', metrics.celery_worker_tasks_active._name, 0,
        )
        # noinspection PyProtectedMember
        logger.debug(
            'Updated gauge=%s value=%s', metrics.celery_worker_up._name, 0,
        )


def _purge_worker_metrics(hostname: str, service_name: str) -> None:                        # noqa: C901,WPS231
    # Prometheus stores a copy of the metrics in memory, so we need to remove them
    # The key of the metrics is a string sequence e.g ('celery(queue_name)', 'host-1(hostname)')
    # noinspection PyProtectedMember
    for label_seq in list(metrics.celery_worker_tasks_active._metrics.keys()):
        if hostname in label_seq and service_name in label_seq:
            metrics.celery_worker_tasks_active.remove(*label_seq)

    # noinspection PyProtectedMember
    for label_seq in list(metrics.celery_worker_up._metrics.keys()):                        # noqa: WPS440
        if hostname in label_seq and service_name in label_seq:
            metrics.celery_worker_up.remove(*label_seq)

    for counter in metrics.events_state_counters.values():
        # noinspection PyProtectedMember
        for label_seq in list(counter._metrics.keys()):                                     # noqa: WPS440
            if hostname in label_seq and service_name in label_seq:
                counter.remove(*label_seq)

    # noinspection PyProtectedMember
    for label_seq in list(metrics.celery_task_runtime._metrics.keys()):                     # noqa: WPS440
        if hostname in label_seq and service_name in label_seq:
            metrics.celery_task_runtime.remove(*label_seq)

    del state.worker_last_seen[(hostname, service_name)]  # noqa: WPS420


def _get_hostname(name: str) -> str:
    """
    Get hostname from celery's hostname.

    Celery's hostname contains either worker's name or Process ID in it.
    >>> _get_hostname("workername@hostname")
    'hostname'
    >>> _get_hostname("gen531@hostname")
    'hostname'

    Prometheus suggests it:
    > Do not use labels to store dimensions with high cardinality (many label values)
    """
    _, hostname = nodesplit(name)
    return hostname


_exception_pattern = re.compile(r'^(\w+)\(')


def _get_exception_class_name(exception_name: str) -> str:
    match = _exception_pattern.match(exception_name)
    if match:
        return match.group(1)
    return 'UnknownException'


def _redis_queue_length(connection: Connection, queue: str) -> int:
    return connection.channel().client.llen(queue)


def _rabbitmq_queue_length(connection: Connection, queue: str) -> int:
    queue_info = _rabbitmq_queue_info(connection, queue)
    if queue_info:
        return queue_info.message_count
    return 0


def _queue_length(transport: str, connection: Connection, queue: str) -> int | None:
    if transport in ['redis', 'rediss', 'sentinel']:                                        # noqa: WPS510
        return _redis_queue_length(connection, queue)

    if transport in ['amqp', 'amqps', 'memory']:                                            # noqa: WPS510
        return _rabbitmq_queue_length(connection, queue)

    return None


def _rabbitmq_queue_consumer_count(connection: Connection, queue: str) -> int:
    queue_info = _rabbitmq_queue_info(connection, queue)
    if queue_info:
        return queue_info.consumer_count
    return 0


def _rabbitmq_queue_info(connection: Connection, queue: str) -> queue_declare_ok_t | None:
    try:
        return connection.default_channel.queue_declare(queue=queue, passive=True)
    except ChannelError as ex:
        if 'NOT_FOUND' in ex.message:
            logger.debug("Queue '$s' not found", queue)
            return None
        raise ex
