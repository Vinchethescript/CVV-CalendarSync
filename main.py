import os
import asyncio
from dotenv import load_dotenv
from cvvsync import CalendarSync
from traceback import print_exception
from aiocvv import ClassevivaClient

load_dotenv()

msg = "{a} added, {e} edited, {d} deleted, {s} already added. Total: {sum}/{t}"


async def on_login(client: ClassevivaClient):
    print(f"Hello, {client.me.first_name}!\n")


async def on_loop_start():
    print("Adding events...")
    print(msg.format(a=0, e=0, d=0, s=0, sum="?", t="?"), end="", flush=True)


async def on_data(added, edited, deleted, skipped, all):
    s = added + edited + deleted + skipped
    print("\r" + msg.format(a=added, e=edited, d=deleted, s=skipped, sum=s, t=all), end="")


async def on_loop_end(added, edited, deleted, skipped, all):
    print("\nDone! Will sleep for 30 minutes.\n")


async def on_error(exc):
    print("Ignoring exception while syncing:")
    print_exception(type(exc), exc, exc.__traceback__)


async def main():
    syncer = CalendarSync(
        os.getenv("CVV_USERNAME"), os.getenv("CVV_PASSWORD"), os.getenv("CVV_IDENTITY")
    )

    syncer.on_cvv_login = on_login
    syncer.on_loop_start = on_loop_start
    syncer.on_data = on_data
    syncer.on_error = on_error
    syncer.on_loop_end = on_loop_end

    print("Logging in...")
    try:
        # this will return a task, in this case we are awaiting
        # it because we want this program to run forever
        await syncer.start()
    except asyncio.CancelledError:
        syncer.stop()


if __name__ == "__main__":
    asyncio.run(main())
