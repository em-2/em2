import pytest

from em2 import Settings

from tests.fixture_classes.push import MockedHttpDNSPusher
from tests.fixture_classes.worker import RaiseWorker

pytest_plugins = 'arq.testing'


@pytest.yield_fixture
def pusher(loop):
    settings = Settings(R_DATABASE=2)

    async def setup(push_class=MockedHttpDNSPusher):
        _pusher = push_class(settings=settings, loop=loop)
        async with await _pusher.get_redis_conn() as redis:
            await redis.flushdb()
        return _pusher

    _pusher = loop.run_until_complete(setup())

    yield _pusher

    loop.run_until_complete(_pusher.close())


async def test_save_nodes_existing(loop, pusher):
    async with await pusher.get_redis_conn() as redis:
        await redis.set(b'nd:123:example.com', b'platform.com')
    await pusher.save_nodes('123', 'foo@example.com')
    worker = RaiseWorker(settings=pusher._settings, batch=True, loop=loop, shadows=[MockedHttpDNSPusher])
    await worker.run()
    async with await pusher.get_redis_conn() as redis:
        domains = await redis.hkeys(b'pc:123')
        assert domains == [b'example.com']
        platforms = await redis.hmget(b'pc:123', *domains)
        assert platforms == [b'platform.com']
