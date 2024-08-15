import os
import asyncio
from dotenv import load_dotenv
from cvvsync import CalendarSync

load_dotenv()

omsg = "Adding events..."
msg = omsg + " {a} added, {e} edited, {d} deleted, {s} skipped"

async def on_loop_start():
    print(omsg, end="")

async def on_data(added, edited, deleted, skipped):
    print("\r" + msg.format(a=added, e=edited, d=deleted, s=skipped), end="")

async def on_loop_end(added, edited, deleted, skipped):
    print("\nDone! Will sleep for 30 minutes.\n")


async def main():
    syncer = CalendarSync(
        os.getenv("CVV_USERNAME"), os.getenv("CVV_PASSWORD"), os.getenv("CVV_IDENTITY")
    )

    syncer.on_loop_start = on_loop_start
    syncer.on_data = on_data
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
