import os
import asyncio
import shelve

from functools import partial
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from datetime import datetime, date
from pytz import timezone
from aiocvv import ClassevivaClient
from aiocvv.dataclasses import Day
from aiocvv.enums import NoteType, EventCode
from dotenv import load_dotenv
from typing import Union, Optional, AsyncGenerator
from appdirs import user_cache_dir

load_dotenv()
DateOrDatetime = Union[date, datetime]
tz = timezone("Europe/Rome")
SHELF_PATH = os.path.join(user_cache_dir(), "cvvsync.db")


def date_to_datetime(date: DateOrDatetime, reset_hours=True) -> datetime:
    if isinstance(date, datetime) and not reset_hours:
        return date.astimezone(tz)

    return datetime(date.year, date.month, date.day, 0, 0, 0, 0, tzinfo=tz)


def gdate_to_datetime(date: str, reset_hours=True) -> datetime:
    try:
        ret = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        ret = datetime.strptime(date, "%Y-%m-%d")

    return date_to_datetime(ret, reset_hours)


class GoogleCalendar:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.service: Resource = None

    async def call_on_func(self, func, meth, *args, **kwargs):
        return await self.loop.run_in_executor(
            None, partial(getattr(func, meth), *args, **kwargs)
        )

    async def call_service(self, method, *args, **kwargs):
        if not self.service:
            self.service = await self.login()

        return await self.call_on_func(self.service, method, *args, **kwargs)

    async def exec_list(self, method, *args, **kwargs):
        if not self.service:
            self.service = await self.login()

        called = await self.call_service(method)
        list = await self.call_on_func(called, "list", *args, **kwargs)
        return await self.call_on_func(list, "execute")

    async def exec_insert(self, method, *args, **kwargs):
        if not self.service:
            self.service = await self.login()

        called = await self.call_service(method)
        insert = await self.call_on_func(called, "insert", *args, **kwargs)
        return await self.call_on_func(insert, "execute")

    async def exec_patch(self, method, *args, **kwargs):
        if not self.service:
            self.service = await self.login()

        called = await self.call_service(method)
        patch = await self.call_on_func(called, "patch", *args, **kwargs)
        return await self.call_on_func(patch, "execute")

    async def exec_delete(self, method, *args, **kwargs):
        if not self.service:
            self.service = await self.login()

        called = await self.call_service(method)
        delete = await self.call_on_func(called, "delete", *args, **kwargs)
        return await self.call_on_func(delete, "execute")

    async def login(self):
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", scopes)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                await self.call_on_func(creds, "refresh", Request())
            else:
                flow = await self.call_on_func(
                    InstalledAppFlow,
                    "from_client_secrets_file",
                    "credentials.json",
                    scopes,
                )
                creds = await self.call_on_func(flow, "run_local_server", port=0)

            with open("token.json", "w") as token:
                token.write(creds.to_json())

        return await self.loop.run_in_executor(
            None, partial(build, "calendar", "v3", credentials=creds)
        )

    async def get_events(
        self, start: DateOrDatetime, end: DateOrDatetime
    ) -> list[dict]:
        if not self.service:
            self.service = await self.login()

        start = date_to_datetime(start).astimezone(tz).isoformat()
        end = date_to_datetime(end).astimezone(tz).isoformat()

        max = 2500
        data = await self.exec_list(
            "events",
            calendarId="primary",
            timeMin=start,
            timeMax=end,
            maxResults=max,
            singleEvents=True,
            orderBy="startTime",
        )
        items = data["items"]
        cont = True
        while items and len(items) % max == 0 and cont:
            next_ = items[-1]["start"]["dateTime"]
            next = gdate_to_datetime(next_).isoformat()
            items = list(filter(lambda x: x["start"]["dateTime"] != next_, items))
            data = await self.exec_list(
                "events",
                calendarId="primary",
                timeMin=next,
                timeMax=end,
                maxResults=max,
                singleEvents=True,
                orderBy="startTime",
            )
            items += data["items"]
            cont = next != end

        return items

    async def add_event(self, payload: dict):
        return await self.exec_insert("events", calendarId="primary", body=payload)

    async def patch_event(self, event_id: str, payload: dict):
        return await self.exec_patch(
            "events", calendarId="primary", eventId=event_id, body=payload
        )

    async def delete_event(self, event_id: str):
        return await self.exec_delete("events", calendarId="primary", eventId=event_id)


class CalendarSync:
    def __init__(self, username: str, password: str, identity: Optional[str] = None):
        self.google = GoogleCalendar()
        self.client = ClassevivaClient(
            os.getenv("CVV_USERNAME"),
            os.getenv("CVV_PASSWORD"),
            os.getenv("CVV_IDENTITY"),
        )
        self.__sync_loop = None
        self.__periods = None
        self.__sleep = 1800  # 30 minutes
        self.__loop_lock = asyncio.Lock()

    @classmethod
    def create_requests(cls, day: Day):
        events = []
        note_titles = {
            NoteType.teacher: "Annotazione",
            NoteType.registry: "Nota disciplinare",
            NoteType.warning: "Richiamo",
            NoteType.sanction: "Sanzione disciplinare",
        }
        event_titles = {
            EventCode.note: "Agenda -",
            EventCode.homework: "Compiti di",
            EventCode.reservation: "Prenotazione aula -",
        }
        for ev in day.agenda:
            name = ev.subject.description if ev.subject else ev.author
            start = None
            end = None
            if ev.full_day:
                start = {
                    "date": cls.datetime_to_date(ev.start).isoformat(),
                }
                end = {
                    "date": cls.datetime_to_date(ev.end).isoformat(),
                }
            else:
                start = {
                    "dateTime": ev.start.isoformat(),
                    "timeZone": "Europe/Rome",
                }
                end = {
                    "dateTime": ev.end.isoformat(),
                    "timeZone": "Europe/Rome",
                }

            events.append(
                {
                    "summary": f"{event_titles[ev.type]} {name}",
                    "description": ev.notes or "",
                    "start": start,
                    "end": end,
                    "reminders": {
                        "useDefault": False,
                        "overrides": [],
                    },
                }
            )

        for note in day.notes:
            events.append(
                {
                    "summary": f"{note_titles[note.type]} - {note.author_name}",
                    "description": note.text,
                    "start": {
                        "date": note.date.isoformat(),
                    },
                    "end": {
                        "date": note.date.isoformat(),
                    },
                    "reminders": {
                        "useDefault": False,
                        "overrides": [],
                    },
                }
            )

        return events

    @staticmethod
    def datetime_to_date(dt: datetime) -> str:
        return date(dt.year, dt.month, dt.day)

    @staticmethod
    def get_calendar_date_value(ev: dict):
        return ev["start"].get("dateTime", ev["start"].get("date"))

    @classmethod
    def filter_date(cls, resp: list[dict], date: DateOrDatetime) -> str:
        return list(
            filter(
                lambda ev: "start" in ev
                and cls.datetime_to_date(
                    gdate_to_datetime(cls.get_calendar_date_value(ev))
                )
                == cls.datetime_to_date(date),
                resp,
            )
        )

    async def login(self):
        if not self.client.me:
            await self.client.login()

        if not self.google.service:
            await self.google.login()

    async def sync(self) -> tuple[int, int]:
        async for added, edited, skipped in self.sync_iter():
            pass

        return added, edited, skipped

    async def sync_iter(self) -> AsyncGenerator[tuple[int, int, int], None]:
        """Synchronize Google Calendar with the Classeviva calendar."""
        await self.login()

        async with self.__loop_lock:
            self.__periods = (
                self.__periods or await self.client.me.calendar.get_periods()
            )
            start_date = datetime(2023, 9, 1, tzinfo=tz)
            end_date = date_to_datetime(self.__periods[-1].end)

            days = await self.client.me.calendar.get_day(start_date, end_date)
            days = sorted(
                filter(lambda x: x.agenda or x.notes, days), key=lambda x: x.date
            )
            calendar = await self.google.get_events(start_date, end_date)
            old_calendar = shelve.open(SHELF_PATH)
            if "items" not in old_calendar:
                old_calendar["items"] = []

            skipped = 0
            edited = 0
            added = 0
            for day in days:
                cday = self.filter_date(calendar, day.date)
                reqs = self.create_requests(day)

                for req in reqs:
                    entries = list(
                        filter(
                            lambda e: e["summary"] == req["summary"]
                            and gdate_to_datetime(
                                self.get_calendar_date_value(e), False
                            )
                            == gdate_to_datetime(
                                self.get_calendar_date_value(req), False
                            ),
                            cday,
                        )
                    )
                    if not entries:
                        await self.google.add_event(req)
                        added += 1
                    elif old_calendar["items"]:
                        # TODO: add support for multiple entries, somehow

                        for entry in entries:
                            old = list(
                                filter(
                                    lambda en: en["iCalUID"] == entry["iCalUID"],
                                    old_calendar["items"],
                                )
                            )[0]
                            if (
                                old["description"].strip()
                                != entry["description"].strip()
                            ):
                                diff = {
                                    k: v for k, v in entry.items() if old.get(k) != v
                                }
                                await self.google.patch_event(old["id"], diff)
                                edited += 1
                    else:
                        skipped += 1

                    yield added, edited, skipped

            old_calendar["items"] = calendar
            old_calendar.close()

    async def background_loop(self):
        while True:
            await self.on_loop_start()
            async for added, edited, skipped in self.sync_iter():
                await self.on_data(added, edited, skipped)

            await self.on_loop_end(added, edited, skipped)
            await asyncio.sleep(self.__sleep)

    def start(self):
        self.__sync_loop = asyncio.create_task(self.background_loop())
        return self.__sync_loop

    def stop(self):
        if self.__sync_loop:
            self.__sync_loop.cancel()
            self.__sync_loop = None

    async def on_data(self, added, edited, skipped):
        pass

    async def on_loop_start(self):
        pass

    async def on_loop_end(self, added, edited, skipped):
        pass


async def main():
    syncer = CalendarSync(
        os.getenv("CVV_USERNAME"), os.getenv("CVV_PASSWORD"), os.getenv("CVV_IDENTITY")
    )

    omsg = "Adding events..."
    msg = omsg + " {a} added, {e} edited, {s} skipped"

    async def on_loop_start():
        print(omsg, end="")

    async def on_data(added, edited, skipped):
        print("\r" + msg.format(a=added, e=edited, s=skipped), end="")

    async def on_loop_end(added, edited, skipped):
        print("\nDone! Will sleep for 30 minutes.\n")

    syncer.on_loop_start = on_loop_start
    syncer.on_data = on_data
    syncer.on_loop_end = on_loop_end

    # awaiting because we want this program to run forever
    print("Logging in...")
    try:
        await syncer.start()
    except asyncio.CancelledError:
        syncer.stop()


if __name__ == "__main__":
    asyncio.run(main())
