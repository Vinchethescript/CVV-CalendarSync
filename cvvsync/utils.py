import os
from datetime import datetime, date
from pytz import timezone as timezone_
from typing import Union
from appdirs import user_cache_dir

DateOrDatetime = Union[date, datetime]
timezone = timezone_("Europe/Rome")
SHELF_PATH = os.path.join(user_cache_dir(), "cvvsync.db")


def date_to_datetime(date: DateOrDatetime, reset_hours=True) -> datetime:
    if isinstance(date, datetime) and not reset_hours:
        return date.astimezone(timezone)

    return datetime(date.year, date.month, date.day, 0, 0, 0, 0, tzinfo=timezone)


def gdate_to_datetime(date: str, reset_hours=True) -> datetime:
    try:
        ret = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        ret = datetime.strptime(date, "%Y-%m-%d")

    return date_to_datetime(ret, reset_hours)
