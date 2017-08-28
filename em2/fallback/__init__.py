import logging
from textwrap import indent

from em2 import Settings
from em2.core import Components, Verbs, Action

logger = logging.getLogger('em2.fallback')


class FallbackHandler:
    footer_message = (
        "You're participating in the em2 conversation {conv_id:.6}. "
        "Reply to this email to contribute to the conversation.\n"
        "You might consider upgrading to email 2.0 to get a greatly improved email experience."
    )

    plain_footer = '\n\n--\n{}\n'.format(footer_message)
    html_footer = ('\n<p style="font-size:small;color:#666;">&mdash;<br>\n'
                   '{}</p>\n'.format(footer_message.replace('\n', '<br>\n')))

    def __init__(self, settings: Settings, loop=None):
        self.settings = settings
        self.loop = loop

    async def startup(self):
        pass

    async def shutdown(self):
        pass

    def get_from_to_bcc(self, action, addresses):
        _from = None
        _to = []
        _bcc = []  # TODO
        for addr in addresses:
            if addr == action.actor:
                _from = addr
            else:
                _to.append(addr)
        return _from, _to, _bcc

    async def push(self, *, action: Action, addresses, conv_subject):
        e_from, to, bcc = self.get_from_to_bcc(action, addresses)
        subject = conv_subject
        # subject = 'Re: ' + conv_subject
        if action.component == Components.MESSAGE:
            if action.verb == Verbs.ADD:
                body = action.body
            else:
                raise NotImplementedError()
        elif action.component == Components.PARTICIPANT:
            if action.verb == Verbs.ADD:
                body = f'adding {action.item} to the conversation'
            elif action.verb == Verbs.DELETE:
                body = f'removing {action.item} from the conversation'
            else:
                raise NotImplementedError()
        msg_id = await self.send_message(
            e_from=e_from,
            to=to,
            bcc=bcc,
            subject=subject,
            plain_body=self.plain_format(body, action.conv_key),
            html_body=self.html_format(body, action.conv_key),
        )
        logger.info('message sent conv %.6s, smtp message id %0.6s', action.conv_key, msg_id)

    async def send_message(self, *, e_from, to, bcc, subject, plain_body, html_body):
        raise NotImplementedError()

    def plain_format(self, body: str, conv_id: str) -> str:
        return body + self.plain_footer.format(conv_id=conv_id)

    def html_format(self, body: str, conv_id: str) -> str:
        # TODO render markdown
        html_body = '\n'.join(f'<p>{l}</p>\n\n' for l in body.split('\n'))
        return html_body + self.html_footer.format(conv_id=conv_id)


class LogFallbackHandler(FallbackHandler):
    async def send_message(self, *, e_from, to, bcc, subject, plain_body, html_body):
        logger.info('%s > %s, subject: "%s"\n%s', e_from, to, subject, indent(plain_body, '  '))
