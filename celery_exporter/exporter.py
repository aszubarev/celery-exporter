import time
from functools import partial
from threading import Thread

import structlog
from celery import Celery
from celery_exporter import metrics, track
from celery_exporter.conf import settings
from celery_exporter.queue_cache import queue_cache
from prometheus_client import start_http_server

logger = structlog.get_logger()


class Exporter:

    SERVICE_NAMES: list[str] = [
        '',    # for default settings of celery
    ]

    def run(self) -> None:
        for service_name in self.SERVICE_NAMES:
            Thread(target=self.collect_worker_metrics, args=(service_name,)).start()
            Thread(target=self.collect_queue_metrics, args=(service_name,)).start()

        Thread(target=self.collect_worker_timeout_metrics).start()

        logger.info('Starting http server. http://0.0.0.0:%s/metrics', settings.PORT)
        start_http_server(port=settings.PORT, registry=metrics.registry)

    @classmethod
    def collect_worker_metrics(cls, service_name: str) -> None:                                     # noqa: C901
        app = cls._create_app(service_name)

        state = app.events.State()
        if settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL:
            logger.debug('Using retry_interval of %s seconds', settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL)

        handlers = {
            'worker-heartbeat': partial(track.track_worker_heartbeat, state=state, service_name=service_name),
            'worker-online': partial(track.track_worker_status, is_online=True, service_name=service_name),
            'worker-offline': partial(track.track_worker_status, is_online=False, service_name=service_name),
        }
        track_task_event = partial(track.track_task_event, state=state, service_name=service_name)

        for key in metrics.state_counters:
            handlers[key] = track_task_event

        with app.connection() as connection:
            while True:                                                                             # noqa: WPS229
                try:                                                                                # noqa: WPS229
                    recv = app.events.Receiver(connection, handlers=handlers)
                    recv.capture(limit=None, timeout=None, wakeup=True)                             # noqa: WPS329
                except (KeyboardInterrupt, SystemExit) as ex:                                       # noqa: WPS329
                    raise ex

                except Exception as e:                                                              # noqa: WPS111
                    logger.exception(
                        'celery-exporter exception %s, retrying in %s seconds.',
                        str(e),
                        settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL,
                    )

                time.sleep(settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL)

    @classmethod
    def collect_queue_metrics(cls, service_name: str) -> None:
        app = cls._create_app(service_name)

        queue_cache[service_name] = set()

        with app.connection() as connection:
            while True:
                try:
                    track.track_queue_metrics(app, connection, queue_cache[service_name], service_name)
                except (KeyboardInterrupt, SystemExit) as ex:                                       # noqa: WPS329
                    raise ex
                except Exception:
                    logger.exception("Can't track queue metrics for service %s", service_name)

                time.sleep(settings.COLLECT_QUEUE_METRICS_INTERVAL)

    @classmethod
    def collect_worker_ping(cls, service_name: str) -> None:
        app = cls._create_app(service_name)

        while True:
            try:
                track.track_worker_ping(app=app, service_name=service_name)
            except (KeyboardInterrupt, SystemExit) as ex:  # noqa: WPS329
                raise ex
            except Exception:
                logger.exception("Can't track worker ping for service %s", service_name)

            time.sleep(settings.COLLECT_WORKER_PING_RETRY_INTERVAL)

    @classmethod
    def collect_worker_timeout_metrics(cls) -> None:
        while True:
            try:
                track.track_timed_out_workers()
            except (KeyboardInterrupt, SystemExit) as ex:                                           # noqa: WPS329
                raise ex
            except Exception:
                logger.exception("Can't track timed_out_workers")

            time.sleep(settings.COLLECT_WORKER_TIMEOUT_METRICS_INTERVAL)

    @classmethod
    def _create_app(cls, service_name: str) -> Celery:
        return Celery(
            broker=settings.BROKER_URL,
            event_exchange=f'{service_name}.{settings.POSTFIX_EVENT_EXCHANGE}',
            control_exchange=service_name,
            control_queue_expires=60,
        )


_instance = Exporter()
run_exporter = _instance.run
