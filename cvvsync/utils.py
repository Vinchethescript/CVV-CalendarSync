import os
import json
from datetime import datetime, date
from pytz import timezone as timezone_
from typing import Union
from appdirs import user_cache_dir

DateOrDatetime = Union[date, datetime]
timezone = timezone_("Europe/Rome")
DESC_FOOTER = "\n\n[[Synced with cvvsync]]"


def get_shelf_path(id: str) -> str:
    dir = user_cache_dir("cvvsync")
    if not os.path.exists(dir):
        os.makedirs(dir)

    return os.path.join(dir, f"{id}.db")


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


def get_boolean_env(name: str) -> bool:
    val = os.getenv(name, None)
    if val is None:
        return False

    val = val.lower()
    if val.isdigit():
        return bool(int(val))

    val = {
        "yes": "true",
        "no": "false",
        "true": "true",
        "false": "false",
        "on": "true",
        "off": "false",
        "y": "true",
        "n": "false",
    }[val]

    return json.loads(val)
