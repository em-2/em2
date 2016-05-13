import asyncio
from aiohttp import web

from .views import act, authenticate


async def finish_controller(app):
    ctrl = app['controller']
    await ctrl.ds.finish()


def create_app(controller, authenticator, loop=None):
    loop = loop or asyncio.get_event_loop()
    app = web.Application(loop=loop)
    app.update(
        controller=controller,
        authenticator=authenticator,
    )

    app.on_cleanup.append(finish_controller)

    # by prefixing all urls with /- we allow a web user interface to be served from the same domain and port
    # without the risk of confusing machine and human urls
    app.router.add_route('POST', '/-/authenticate', authenticate)

    url = '/-/{con:[a-z0-9]+}/{component:[a-z]+}/{verb:[a-z]+}/{item:[a-z0-9]*}'
    app.router.add_route('POST', url, act)

    return app
