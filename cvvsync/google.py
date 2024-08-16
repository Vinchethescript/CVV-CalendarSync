import os
import asyncio

from functools import partial
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from pytz import timezone
from .utils import gdate_to_datetime, date_to_datetime, DateOrDatetime, timezone


class GoogleCalendar:
    def __init__(
        self,
        creds_path: str = "credentials.json",
        token_path: str = "token.json",
        loop: asyncio.AbstractEventLoop = None,
    ):
        self.loop = loop or asyncio.get_event_loop()
        self.service: Resource = None
        self.creds_path = creds_path
        self.token_path = token_path

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
        if os.path.exists(self.token_path):
            creds = await self.call_on_func(
                Credentials, "from_authorized_user_file", self.token_path, scopes
            )

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

        start = date_to_datetime(start).astimezone(timezone).isoformat()
        end = date_to_datetime(end).astimezone(timezone).isoformat()

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
