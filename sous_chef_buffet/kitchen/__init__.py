import asyncio
from typing import Any, Coroutine


def _run_async(fn: Coroutine) -> Any:
    """Create an ephemeral event loop and run the provided coroutine.
    
    This is primarily intended for testing asynchronous functions from the REPL
    and is not meant to be referenced elsewhere in the code.
    """

    loop = asyncio.new_event_loop()
    task = loop.create_task(fn)
    results = loop.run_until_complete(task)
    
    return results
   