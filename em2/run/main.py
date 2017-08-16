#!/usr/bin/env python3.6
import asyncio
import os
import sys

from em2 import VERSION, Settings
from em2.logging import logger, setup_logging
from em2.run.check import command, execute
from em2.run.database import prepare_database as _prepare_database
from em2.utils.network import wait_for_services

# imports are local where possible so commands (especially check) are as fast to run as possible


@command
def web(settings):
    import uvloop
    from aiohttp.web import run_app
    from em2 import create_app
    # print(settings.to_string(True), flush=True)

    asyncio.get_event_loop().close()
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    loop = asyncio.get_event_loop()

    wait_for_services(settings, loop=loop)
    loop.run_until_complete(_prepare_database(settings, overwrite_existing=False))

    logger.info('starting server...')
    app = create_app(settings)
    run_app(app, port=settings.WEB_PORT, loop=loop, print=lambda v: None, access_log=None, shutdown_timeout=5)


@command
def prepare_database(settings):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_prepare_database(settings, True))  # TODO require argument for force


@command
def worker(settings):
    from arq import RunWorkerProcess

    loop = asyncio.get_event_loop()
    wait_for_services(settings, loop=loop)
    loop.run_until_complete(_prepare_database(settings, overwrite_existing=False))

    RunWorkerProcess('em2.worker', 'Worker')


@command
def info(settings):
    import aiohttp
    import arq
    logger.info(f'em2')
    logger.info(f'Python:   {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')
    logger.info(f'em2:      {VERSION}')
    logger.info(f'aiohttp:  {aiohttp.__version__}')
    logger.info(f'arq:      {arq.VERSION}\n')
    logger.info(f'domain:   {settings.LOCAL_DOMAIN}')
    logger.info(f'command:  {settings.COMMAND}')
    logger.info(f'debug:    {settings.DEBUG}')
    logger.info(f'pg db:    {settings.PG_NAME}')
    logger.info(f'redis db: {settings.R_DATABASE}\n')
    # try:
    #     loop = asyncio.get_event_loop()
    #     from em2.ds.pg.utils import check_database_exists
    #     wait_for_services(settings, loop=loop)
    #     check_database_exists(settings)
    #
    #     loop.run_until_complete(_list_conversations(settings, loop, logger))
    # except Exception as e:
    #     logger.warning(f'Error get conversation list {e.__class__.__name__}: {e}')


@command
def shell():
    """
    Basic replica of django-extensions shell, ugly but very useful in development
    """
    EXEC_LINES = [
        'import asyncio, os, re, sys',
        'from datetime import datetime, timedelta, timezone',
        'from pathlib import Path',
        '',
        'from em2 import Settings',
        'from em2.core import Controller',
        '',
        'loop = asyncio.get_event_loop()',
        'await_ = loop.run_until_complete',
        'settings = Settings()',
        'ctrl = Controller(settings=settings, loop=loop)',
        'await_(ctrl.startup())',
    ]
    EXEC_LINES += (
        ['print("\\n    Python {v.major}.{v.minor}.{v.micro}\\n".format(v=sys.version_info))'] +
        [f'print("    {l}")' for l in EXEC_LINES]
    )

    from IPython import start_ipython
    from IPython.terminal.ipapp import load_default_config
    c = load_default_config()

    c.TerminalIPythonApp.display_banner = False
    c.TerminalInteractiveShell.confirm_exit = False
    c.InteractiveShellApp.exec_lines = EXEC_LINES
    start_ipython(argv=(), config=c)


def main():
    # special cases where we use arguments so you don't have to mess with env variables.
    argument = sys.argv[-1]
    if argument in ('info', 'shell'):
        settings = Settings()
        setup_logging(settings)
        if argument == 'info':
            logger.info('running info based on argument...')
            info(settings)
        else:
            logger.info('running shell based on argument...')
            shell()
    else:
        command_ = os.getenv('EM2_COMMAND', 'info')
        execute(command_)


if __name__ == '__main__':
    main()