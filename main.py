import os
import json
import asyncio
from dotenv import load_dotenv
from cvvsync import CalendarSync
from traceback import print_exception
from aiocvv import ClassevivaClient

load_dotenv()


def get_msg(added, edited, deleted, skipped, all):
    p = lambda n: (n / all) * 100 if all else 0
    can = all != "?"
    s = added + edited + deleted + skipped
    pc = f" ({p(s):.2f}%)" if can else ""

    if added and can:
        added = f"{added} ({p(added):.2f}%)"

    if edited and can:
        edited = f"{edited} ({p(edited):.2f}%)"

    if deleted and can:
        deleted = f"{deleted} ({p(deleted):.2f}%)"

    if skipped and can:
        skipped = f"{skipped} ({p(skipped):.2f}%)"

    return (
        f"{added} added, {edited} edited, {deleted} deleted, "
        f"{skipped} skipped. Total: {s}/{all}{pc}"
    )


async def on_login(client: ClassevivaClient):
    print(f"Hello, {client.me.first_name}!\n")


async def on_loop_start():
    print("Adding events...")
    print(get_msg(0, 0, 0, 0, "?"), end="", flush=True)


async def on_data(added, edited, deleted, skipped, all):
    print("\r" + get_msg(added, edited, deleted, skipped, all), end="")


async def on_loop_end(added, edited, deleted, skipped, all):
    print("\nDone! Will sleep for 30 minutes.\n")


async def on_error(exc):
    print("Ignoring exception while syncing:")
    print_exception(type(exc), exc, exc.__traceback__)


async def main():
    # PM2 compatibility
    if os.getenv("PM2_HOME") and os.path.exists(".git"):

        async def get_version() -> str:
            vers = await asyncio.create_subprocess_shell(
                'git log -1 --format="%h" --abbrev=7 | xargs',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            o, e = await vers.communicate()
            o, e = o.decode().strip(), e.decode().strip()
            if e:
                print(e)
                return

            return o

        def upd_version(version: str):
            data = {"version": version}
            with open("package.json", "w") as f:
                json.dump(data, f, indent=2)

        v = await get_version()
        if not os.path.exists("package.json"):
            upd_version(v)
        elif json.load(open("package.json"))["version"] != v:
            upd_version(v)

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
