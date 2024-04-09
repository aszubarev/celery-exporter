import time
from functools import partial
from threading import Thread

import structlog
from celery import Celery
from celery_exporter import metrics, track
from celery_exporter.conf import settings
from celery_exporter.utils.celery_app_settings import CeleryAppSettings
from prometheus_client import start_http_server

logger = structlog.get_logger()


class Exporter:

    CONFIGURATION: dict[str, CeleryAppSettings] = {
        'default': CeleryAppSettings(
            broker_url=settings.BROKER_URL,
        ),
        'service_a': CeleryAppSettings(
            broker_url=settings.BROKER_URL,
            task_default_exchange='service_a',
            task_default_queue='service_a',
            event_exchange='service_a.celeryev',
            event_queue_prefix='service_a.celeryev',
            control_exchange='service_a',
        ),
    }

    def run(self) -> None:
        for service_name in self.CONFIGURATION:
            Thread(target=self.collect_worker_metrics, args=(service_name,)).start()
            Thread(target=self.collect_queue_metrics, args=(service_name,)).start()

        Thread(target=self.collect_worker_timeout).start()

        logger.info('Starting http server. http://0.0.0.0:%s/metrics', settings.PORT)
        start_http_server(port=settings.PORT, registry=metrics.registry)

    @classmethod
    def collect_worker_metrics(cls, service_name: str) -> None:                                     # noqa: C901
        app = cls._create_celery_app(service_name)

        if settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL:
            logger.debug('Using retry_interval of %s seconds', settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL)

        handlers = {
            'worker-heartbeat': partial(track.track_worker_heartbeat, service_name=service_name),
            'worker-online': partial(track.track_worker_status, service_name=service_name),
            'worker-offline': partial(track.track_worker_status, service_name=service_name),
        }
        track_task_event = partial(track.track_task_event, service_name=service_name)

        for key in metrics.events_state_counters:
            handlers[key] = track_task_event

        with app.connection() as connection:
            while True:
                try:                                                                                # noqa: WPS229
                    recv = app.events.Receiver(connection, handlers=handlers)
                    recv.capture(limit=None, timeout=None, wakeup=True)
                except (KeyboardInterrupt, SystemExit) as ex:                                       # noqa: WPS329
                    raise ex
                except Exception:
                    logger.exception(
                        'Handle exception',
                        retry_interval=settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL,
                    )

                time.sleep(settings.COLLECT_WORKER_METRICS_RETRY_INTERVAL)

    @classmethod
    def collect_queue_metrics(cls, service_name: str) -> None:
        app = cls._create_celery_app(service_name)

        with app.connection() as connection:
            while True:
                try:
                    track.track_queue_metrics(app, connection, service_name)
                except (KeyboardInterrupt, SystemExit) as ex:                                       # noqa: WPS329
                    raise ex
                except Exception:
                    logger.exception("Can't track queue metrics for service %s", service_name)

                time.sleep(settings.COLLECT_QUEUE_METRICS_INTERVAL)

    @classmethod
    def collect_worker_timeout(cls) -> None:
        while True:
            try:
                track.track_worker_timeout()
            except (KeyboardInterrupt, SystemExit) as ex:                                           # noqa: WPS329
                raise ex
            except Exception:
                logger.exception("Can't track timed_out_workers")

            time.sleep(settings.COLLECT_WORKER_TIMEOUT_METRICS_INTERVAL)

    @classmethod
    def _create_celery_app(cls, service_name: str) -> Celery:
        celery_app_settings = cls.CONFIGURATION[service_name].dict(exclude_unset=True)
        logger.debug('Create celery app', service_name=service_name, celery_app_settings=celery_app_settings)
        return Celery(**celery_app_settings)


_instance = Exporter()

run = _instance.run
