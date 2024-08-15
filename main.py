import os
import asyncio
from dotenv import load_dotenv
from cvvsync import CalendarSync

load_dotenv()


async def main():
    syncer = CalendarSync(
        os.getenv("CVV_USERNAME"), os.getenv("CVV_PASSWORD"), os.getenv("CVV_IDENTITY")
    )

    omsg = "Adding events..."
    msg = omsg + " {a} added, {e} edited, {d} deleted, {s} skipped"

    async def on_loop_start():
        print(omsg, end="")

    async def on_data(added, edited, deleted, skipped):
        print("\r" + msg.format(a=added, e=edited, d=deleted, s=skipped), end="")

    async def on_loop_end(added, edited, deleted, skipped):
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
