from pprint import pp
import pandas as pd
from lxml import etree
import requests


from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import state
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware

from config import OLAP_login, OLAP_pwd
from iiko import IikoCardAPI
from tg_const import ALLOWED_IDs, MODIFY_ACTIONS
from tg_kbds import std_kbd
from tg_init import bot


class ClientStatesGroup(state.StatesGroup):
    search_card = state.State()
    add_custom_surname = state.State()
    add_custom_name = state.State()
    add_card = state.State()
    add_track = state.State()
    customer = state.State()
    set_data = state.State()
    set_card = state.State()
    select_date_start = state.State()
    select_date_end = state.State()


class StepsForm(state.StatesGroup):
    select_card = state.State()
    select_date_start = state.State()
    select_date_end = state.State()


async def store_customer_data(state: FSMContext, customer):
    async with state.proxy() as data:
        data['customer'] = customer['id']
        data['phone'] = customer['phone']
        data['full_name'] = f"{customer['surname']} {customer['name'] if customer['name'] else ''} {customer['middleName'] if customer['middleName'] else ''}"
        data['name'] = customer['name'] if customer['name'] else ''
        data['surname'] = customer['surname']
        data['middleName'] = customer['middleName'] if customer['middleName'] else ''
        if customer['walletBalances']:
            # data['balance'] = customer['walletBalances'][0]['balance']
            data['wallets'] = customer['walletBalances']
        else:
            # data['balance'] = "Отсутствует"
            data['wallets'] = None
        if customer['categories']:
            data['categories'] = customer['categories']
        else:
            data['categories'] = None


def get_allowed(user_id) -> bool:
    return user_id in ALLOWED_IDs


async def connect(message: types.Message, iiko: IikoCardAPI):
    iiko.set_token()
    if iiko.token:
        await message.answer('Подключено!', reply_markup=std_kbd)
    else:
        await message.answer('Подключиться не получилось...')


class CheckMiddleware(BaseMiddleware):
    async def on_process_update(self, update: types.Update, data: dict):
        user_id = 0
        try:
            user_id = update.message.chat.id
        except AttributeError:
            try:
                user_id = update.callback_query.message.chat.id
            except Exception as ex:
                print(f"[ERROR]: {ex}")
                pp(list(update))
        except Exception as ex:
            print(f"[ERROR]: {ex}")
            pp(list(update))
        if not get_allowed(user_id):
            await bot.send_message(user_id, "Вам недоступно взаимодействие с этим ботом. Извините!")
            raise CancelHandler()


def chunk_data(data: pd.DataFrame, lines=10) -> list:
    pos = 0
    end_pos = len(data)
    new_data = []
    while pos < end_pos:
        new_data.append(data.iloc[pos:pos+lines])
        pos += lines
    return new_data


def chunk_data_by_field(data: pd.DataFrame, field) -> list[pd.DataFrame]:
    stamps = sorted(list(set(data[field])))
    out_data = []
    for stamp in stamps:
        out_data.append(data[data[field] == stamp])
    return out_data


async def form_customer_personal_data_from_state(state: FSMContext) -> str:
    request = ""
    async with state.proxy() as data:
        for action in MODIFY_ACTIONS:
            request += f"{MODIFY_ACTIONS[action]}: {data[action]}\n"
    request += f"Что хотите изменить(добавить)?"
    return request


def form_check_cats_and_progs(customer) -> str:
    result = ""
    if not customer['walletBalances']:
        result += "⚠️ ВНИМАНИЕ! У пользователя отсутствуют кошельки(пользователь не включен ни в одну программу)!\n"
    if not customer['categories']:
        result += "⚠️ ВНИМАНИЕ! Пользователь не включен ни в одну категорию!\n"
    return result


def get_olap_data(card, start_date, end_date) -> pd.DataFrame:
    session = requests.Session()

    payload = {'j_username': OLAP_login, 'j_password': OLAP_pwd}
    session.post('https://forvard-co.iiko.it/resto/j_spring_security_check', data=payload)
    transform = etree.XSLT(
        etree.fromstring(session.get('https://forvard-co.iiko.it/resto/service/reports/report-view.xslt').text))
    report = session.post(
        f'https://forvard-co.iiko.it/resto/service/reports/report.jspx?dateFrom={start_date.strftime("%d.%m.%Y")}&dateTo={end_date.strftime("%d.%m.%Y")}&presetId=c902622a-3006-4744-a562-ba1e562445cc').text
    newdom = transform(etree.fromstring(report))
    session.close()

    data = pd.read_html(etree.tostring(newdom), converters={'Номер карты клиента': str})[0]
    return data[data['Номер карты клиента'] == card][
        ['Время закрытия', 'Номер чека', 'Группа', 'Блюдо', 'Количество блюд', 'Сумма без скидки']]



