import os
import asyncio

from functools import partial
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from datetime import datetime, date, timedelta
from pytz import timezone
from aiocvv import ClassevivaClient
from aiocvv.dataclasses import Day
from aiocvv.enums import NoteType, EventCode, SchoolDayStatus
from dotenv import load_dotenv
from typing import Union


load_dotenv()
DateOrDatetime = Union[date, datetime]
tz = timezone("Europe/Rome")


def date_to_datetime(date: DateOrDatetime) -> datetime:
    return datetime(date.year, date.month, date.day, 0, 0, 0, 0, tzinfo=tz)


def gdate_to_datetime(date: str) -> datetime:
    try:
        ret = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        ret = datetime.strptime(date, "%Y-%m-%d")

    return date_to_datetime(ret)


def datetime_to_date(dt: datetime) -> str:
    return date(dt.year, dt.month, dt.day)


def get_calendar_date_value(ev: dict):
    return ev["start"].get("dateTime", ev["start"].get("date"))


def filter_date(resp: list[dict], date: DateOrDatetime) -> str:

    return list(
        filter(
            lambda ev: "start" in ev
            and datetime_to_date(gdate_to_datetime(get_calendar_date_value(ev)))
            == datetime_to_date(date),
            resp,
        )
    )


def create_requests(day: Day):
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
                "date": datetime_to_date(ev.start).isoformat(),
            }
            end = {
                "date": datetime_to_date(ev.end).isoformat(),
            }

        events.append(
            {
                "summary": f"{event_titles[ev.type]} {name}",
                "description": ev.notes or "",
                "start": start or {
                    "dateTime": ev.start.isoformat(),
                    "timeZone": "Europe/Rome",
                },
                "end": end or {
                    "dateTime": ev.end.isoformat(),
                    "timeZone": "Europe/Rome",
                },
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

    async def get_events(self, start: DateOrDatetime, end: DateOrDatetime) -> list[dict]:
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
        while len(items) % max == 0 and cont:
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


async def main():
    gc = GoogleCalendar()
    client = ClassevivaClient(
        os.getenv("CVV_USERNAME"), os.getenv("CVV_PASSWORD"), os.getenv("CVV_IDENTITY")
    )
    await client.login()

    periods = await client.me.calendar.get_periods()
    start_date = datetime(2023, 9, 1, tzinfo=tz)
    end_date = date_to_datetime(periods[-1].end)

    days = await client.me.calendar.get_day(start_date, end_date)
    days = sorted(days, key=lambda x: x.date)
    calendar = await gc.get_events(start_date, end_date)

    for day in days:
        cday = filter_date(calendar, day.date)
        reqs = create_requests(day)

        if not reqs:
            print(f"Day {day.date.isoformat()} has no events.\n\n")
            continue

        if not cday:
            print("No events in GCalendar for this day.")

        print(f"================ {day.date.isoformat()} ================")

        for req in reqs:
            # BUG: if something has been edited, a new one will be created in GCalendar
            # also, if an event (not homework!) is edited, the edit won't be applied here
            if not any(
                e["summary"] == req["summary"]
                and gdate_to_datetime(get_calendar_date_value(e))
                == gdate_to_datetime(get_calendar_date_value(req))
                for e in cday
            ):
                print(f"{req['summary']}\n{req['description']}\n")
                await gc.add_event(req)
            else:
                print(f"Skipping {req['summary']}")

        print("\n\n")


if __name__ == "__main__":
    asyncio.run(main())
