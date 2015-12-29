import pytest
import socket

import aiohttp
from aiohttp import web

from em2.base import Controller
from em2.http_server import Api
from tests.py_datastore import SimpleDataStore


@pytest.fixture
def port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.yield_fixture
def server(loop, port):
    app = handler = srv = None

    async def create(*, debug=False, ssl_ctx=None, proto='http'):
        nonlocal app, handler, srv
        app = web.Application(loop=loop)

        ds = SimpleDataStore()
        ctrl = Controller(ds)
        Api(app, ctrl)

        handler = app.make_handler(debug=debug, keep_alive_on=False)
        srv = await loop.create_server(handler, '127.0.0.1', port, ssl=ssl_ctx)
        if ssl_ctx:
            proto += 's'
        url = '{}://127.0.0.1:{}'.format(proto, port)
        print('\nServer started at {}'.format(url))
        return app, url

    yield create

    async def finish():
        await handler.finish_connections()
        await app.finish()
        srv.close()
        await srv.wait_closed()

    loop.run_until_complete(finish())


class Client:
    def __init__(self, loop, url):
        self._session = aiohttp.ClientSession(loop=loop)
        if not url.endswith('/'):
            url += '/'
        self.url = url

    def close(self):
        self._session.close()

    def get(self, path, **kwargs):
        while path.startswith('/'):
            path = path[1:]
        url = self.url + path
        return self._session.get(url, **kwargs)

    def post(self, path, **kwargs):
        while path.startswith('/'):
            path = path[1:]
        url = self.url + path
        return self._session.post(url, **kwargs)

    def ws_connect(self, path, **kwargs):
        while path.startswith('/'):
            path = path[1:]
        url = self.url + path
        return self._session.ws_connect(url, **kwargs)


@pytest.yield_fixture
def client(loop, server):
    app, url = loop.run_until_complete(server())
    client = Client(loop, url=url)
    yield client

    client.close()
