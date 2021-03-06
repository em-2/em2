from em2.core import Database


class FakeConn:
    async def execute(self, *args, **kwargs):
        pass


class DummyAcquireContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TestDatabase(Database):
    def __init__(self, loop, settings):
        super().__init__(loop, settings)
        self.conn = getattr(settings, '_test_conn', FakeConn())

    async def startup(self):
        pass

    def acquire(self, *, timeout=None):
        return DummyAcquireContext(self.conn)

    async def close(self):
        pass
