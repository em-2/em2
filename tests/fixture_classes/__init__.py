# flake8: noqa
from asyncio import Future, TimeoutError, new_event_loop
import aiohttp

from .auth import SimpleAuthenticator
from .dns_resolver import PLATFORM, TIMESTAMP, VALID_SIGNATURE, get_private_key_file
from .db import TestDatabase
from .fallback import TestFallbackHandler
from .foreign_server import create_test_app
from .push import DNSMockedPusher


def future_result(loop, result):
    r = Future(loop=loop)
    r.set_result(result)
    return r


async def _internet_connected():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head('http://www.google.com', timeout=0.1) as r:
                return 200 <= r.status < 400
    except (OSError, TimeoutError):
        return False


loop = new_event_loop()

INTERNET_CONNECTED = loop.run_until_complete(_internet_connected())
