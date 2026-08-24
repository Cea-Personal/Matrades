from __future__ import annotations

import asyncio
import signal

from modules.agents.runtime import AgentRuntimeRouter


async def serve() -> None:
    router = AgentRuntimeRouter.from_settings()
    await router.start()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    await stopped.wait()
    await router.close()


if __name__ == "__main__":
    asyncio.run(serve())
