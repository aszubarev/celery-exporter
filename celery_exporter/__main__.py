import logging

import click
import structlog
from celery_exporter.conf import settings
from celery_exporter.exporter import run
from celery_exporter.help import cmd_help


@click.command(help=cmd_help)
def cli() -> None:
    run()


if __name__ == '__main__':
    LOG_LEVEL = getattr(logging, settings.LOG_LEVEL)

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(LOG_LEVEL),
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.dict_tracebacks,
            structlog.processors.TimeStamper(fmt='iso'),
            structlog.processors.EventRenamer('message'),
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.PATHNAME,
                    structlog.processors.CallsiteParameter.PROCESS,
                    structlog.processors.CallsiteParameter.PROCESS_NAME,
                },
            ),
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
    )

    cli()
