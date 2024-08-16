import asyncio
import shelve

from .utils import (
    gdate_to_datetime,
    date_to_datetime,
    DateOrDatetime,
    timezone,
    get_shelf_path,
    DESC_FOOTER,
)
from .google import GoogleCalendar
from datetime import datetime, date
from aiocvv import ClassevivaClient
from aiocvv.dataclasses import Day
from aiocvv.enums import NoteType, EventCode
from typing import Optional, AsyncGenerator


class CalendarSync:
    def __init__(
        self,
        username: str,
        password: str,
        identity: Optional[str] = None,
        sleep: int = 1800,  # 30 minutes
        *,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
        loop: asyncio.AbstractEventLoop = None,
    ):
        self.loop = loop or asyncio.get_event_loop()
        self.google = GoogleCalendar(credentials_path, token_path, loop)
        self.client = ClassevivaClient(username, password, identity, loop=loop)
        self.__sync_loop = None
        self.__periods = None
        self.__sleep = sleep
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
            EventCode.note: "{0} - Agenda",
            EventCode.homework: "Compiti di {0}",
            EventCode.reservation: "Prenotazione aula - {0}",
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
                    "summary": event_titles[ev.type].format(name),
                    "description": (ev.notes or "") + DESC_FOOTER,
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
                    "description": note.text + DESC_FOOTER,
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
            try:
                await self.on_cvv_login(self.client)
            except Exception as exc:
                await self.on_error(exc)

        if not self.google.service:
            await self.google.login()

    async def sync(self) -> tuple[int, int, int, int]:
        async for added, edited, deleted, skipped, all in self.sync_iter():
            pass

        return added, edited, deleted, skipped, all

    async def sync_iter(self) -> AsyncGenerator[tuple[int, int, int, int], None]:
        """Synchronize Google Calendar with the Classeviva calendar."""
        old_calendar = None
        async with self.__loop_lock:
            try:
                await self.login()
                self.__periods = (
                    self.__periods or await self.client.me.calendar.get_periods()
                )
                start_date = datetime(2023, 9, 1, tzinfo=timezone)
                end_date = date_to_datetime(self.__periods[-1].end)

                days = await self.client.me.calendar.get_day(start_date, end_date)
                days = sorted(
                    filter(lambda x: x.agenda or x.notes, days), key=lambda x: x.date
                )
                calendar = await self.google.get_events(start_date, end_date)
                calendar = list(
                    filter(
                        lambda ev: ev["description"].endswith(DESC_FOOTER),
                        calendar,
                    )
                )
                old_calendar = shelve.open(get_shelf_path(self.client.me.identity))

                if "items" not in old_calendar:
                    old_calendar["items"] = []

                skipped = 0
                deleted = 0
                edited = 0
                added = 0
                all = len([d for day in days for d in (day.notes + day.agenda)])

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
                        items_to_delete = list(
                            filter(
                                lambda e: e["summary"]
                                not in map(lambda x: x["summary"], reqs),
                                cday,
                            )
                        )

                        # untested but should work
                        if items_to_delete:
                            for item in items_to_delete:
                                await self.google.delete_event(item["id"])
                                deleted += 1
                        elif not entries:
                            await self.google.add_event(req)
                            added += 1
                        elif old_calendar["items"]:
                            for entry in entries:
                                old = list(
                                    filter(
                                        lambda en: en["iCalUID"] == entry["iCalUID"],
                                        old_calendar["items"],
                                    )
                                )[0]
                                diff = {
                                    k: v for k, v in entry.items() if old.get(k) != v
                                }

                                if diff:
                                    await self.google.patch_event(old["id"], diff)
                                    edited += 1
                                else:
                                    skipped += 1
                        else:
                            skipped += 1

                        all += (len(entries) - 1) if len(entries) >= 1 else 0
                        yield added, edited, deleted, skipped, all

                old_calendar["items"] = calendar
            except Exception as exc:
                await self.on_error(exc)
            finally:
                if old_calendar:
                    old_calendar.close()

            return

    async def __background_loop(self):
        await self.login()
        tasks = []
        while True:
            tasks.append(self.loop.create_task(self.on_loop_start()))
            async for added, edited, deleted, skipped, all in self.sync_iter():
                await self.on_data(added, edited, deleted, skipped, all)

            tasks.append(
                self.loop.create_task(
                    self.on_loop_end(added, edited, deleted, skipped, all)
                )
            )
            _, p = await asyncio.wait(
                [self.loop.create_task(asyncio.sleep(self.__sleep)), *tasks],
                return_when=asyncio.ALL_COMPLETED,
            )
            tasks = list(p)

    def start(self) -> asyncio.Task:
        self.__sync_loop = self.loop.create_task(
            self.__background_loop(), name="cvvsync_loop"
        )
        return self.__sync_loop

    def stop(self):
        if self.__sync_loop:
            self.__sync_loop.cancel()
            self.__sync_loop = None

    async def on_cvv_login(self, client: ClassevivaClient):
        pass

    async def on_data(self, added: int, edited: int, deleted: int, skipped: int):
        pass

    async def on_loop_start(self):
        pass

    async def on_loop_end(self, added: int, edited: int, deleted: int, skipped: int):
        pass

    async def on_error(self, exc: BaseException):
        raise exc
