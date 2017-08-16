from aiohttp.web import HTTPBadRequest, HTTPForbidden
from cryptography.fernet import InvalidToken

from em2.core import get_create_recipient
from em2.utils.encoding import msg_decode, msg_encode
from em2.utils.web import db_conn_middleware

from .common import Session


async def user_middleware(app, handler):
    async def user_middleware_handler(request):
        token = request.cookies.get(app['settings'].COOKIE_NAME, '')
        try:
            raw_data = app['fernet'].decrypt(token.encode())
        except InvalidToken:
            raise HTTPForbidden(text='Invalid token')
        try:
            data = msg_decode(raw_data)
            request['session'] = Session(**data)
        except (ValueError, TypeError):
            raise HTTPBadRequest(text='bad cookie data')
        return await handler(request)
    return user_middleware_handler


GET_RECIPIENT_ID = 'SELECT id FROM recipients WHERE address = $1'
# pointless update is slightly ugly, but should happen vary rarely.
SET_RECIPIENT_ID = """
INSERT INTO recipients (address) VALUES ($1)
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address RETURNING id
"""


async def set_recipient(request):
    if request['session'].recipient_id:
        return
    recipient_id = await get_create_recipient(request['conn'], request['session'].address)
    request['session'].recipient_id = recipient_id
    request['session_change'] = True


async def update_session_middleware(app, handler):
    async def _handler(request):
        await set_recipient(request)
        response = await handler(request)

        if request.get('session_change'):
            data = msg_encode(request['session'].values())
            token = app['fernet'].encrypt(data).decode()
            response.set_cookie(app['settings'].COOKIE_NAME, token)

        return response
    return _handler


middleware = (
    user_middleware,
    db_conn_middleware,
    update_session_middleware,
)
