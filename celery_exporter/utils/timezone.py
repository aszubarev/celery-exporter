from datetime import datetime

import pytz


def now():
    return datetime.utcnow().replace(tzinfo=pytz.UTC)


def localtime(timezone=None):
    value = now()

    if timezone is None:
        timezone = pytz.UTC

    return value.astimezone(timezone)
