import asyncio

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.webhook import get_new_configured_app

from config import TOKEN_API, apiLogin, TAISHET_Login
from iiko import IikoCardAPI

loop = asyncio.get_event_loop()
bot = Bot(TOKEN_API, loop=loop)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
my_iiko = IikoCardAPI(TAISHET_Login, 240)  # Создание класса работы с Iiko

WEBHOOK_PATH = f"/{TOKEN_API}"
WEBHOOK_HOST = 'fmservice.g-service.ru'

WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"

dp.middleware.setup(LoggingMiddleware())

app = get_new_configured_app(dispatcher=dp, path=WEBHOOK_PATH)
