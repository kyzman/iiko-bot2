from aiohttp import web
from datetime import datetime, timedelta
import re, concurrent.futures
import logging as log

from asyncio import sleep

from aiogram import executor, types
from aiogram.dispatcher import FSMContext

from tg_init import bot, dp, my_iiko, app, WEBHOOK_PATH, WEBHOOK_URL

from tg_kbds import usr_kbd, std_kbd, get_card_kbd, get_confirm_kbd, modify_ikb, get_customer_kbd, get_olaps_kbd
from tg_const import MODIFY_ACTIONS, HELP_COMMAND, PHONE_TEMPLATE, TRACK_TEMPLATE
from tg_utils import (connect, ClientStatesGroup,
                      store_customer_data, CheckMiddleware, chunk_data_by_field,
                      form_customer_personal_data_from_state, form_check_cats_and_progs, get_olap_data)


WEBHOOK = False  # для запуска в режиме webhook на сервере изменить на True
                 # для запуска в режиме отладки на персональной машине изменить на False


async def on_startup(_):
    if WEBHOOK:
        await bot.set_webhook("https://fmservice.g-service.ru" + WEBHOOK_PATH)
        webhook = await bot.get_webhook_info()
        if webhook.url != WEBHOOK_URL:
            # If URL doesnt match current - remove webhook
            if not webhook.url:
                await bot.delete_webhook()

            # Set new URL for webhook
            await bot.set_webhook(WEBHOOK_URL)

    # my_iiko.set_token()  # Получение токена для работы с Iiko
    location = my_iiko.organizations(True)['organizations']  # получения списка организаций (она должна быть одна!)
    log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} Auto select organization: {location[0]['name']}")  #
    my_iiko.set_organization(location[0]['id'])  # Установка 1ой организации в списке (а других и не должно быть!)
    # await ClientStatesGroup.start.set()


async def on_shutdown(app):
    """
    Graceful shutdown. This method is recommended by aiohttp docs.
    """
    # Remove webhook.
    await bot.delete_webhook()

    # Close Redis connection(if exists).
    await dp.storage.close()
    await dp.storage.wait_closed()


@dp.message_handler(commands=['help'], state='*')
async def help_command(message: types.Message):
    await bot.send_message(chat_id=message.from_user.id, text=HELP_COMMAND, parse_mode="HTML",
                           reply_markup=types.ReplyKeyboardRemove())
    await message.delete()


@dp.message_handler(commands=['organizations'])
async def show_orgs(message: types.Message):
    ikb = types.InlineKeyboardMarkup(row_width=1)
    try:
        for o in my_iiko.organizations()['organizations']:
            ikb.add(types.InlineKeyboardButton(text=o['name'], callback_data=f"organiz_{o['id']}"))
    except KeyError:
        ikb.add(types.InlineKeyboardButton(text="Отмена", callback_data="organiz_"))
    except Exception:
        ikb.add(types.InlineKeyboardButton(text="Подключиться", callback_data='connect'))
    await bot.send_message(chat_id=message.from_user.id, text="Установите организацию для работы.", reply_markup=ikb)


@dp.message_handler(commands=['card', 'start'])
async def show_customer(message: types.Message):
    if not my_iiko.organization_id:  # если по какой-то причине оказалось что организация не выбрана...
        await message.answer('Сначала надо выбрать организацию!')
        await show_orgs(message)
    else:
        await message.answer('Введите номер карты пользователя:')
        await ClientStatesGroup.search_card.set()


@dp.callback_query_handler(lambda callback: callback.data.startswith('organiz_'), state='*')
async def set_org(callback: types.CallbackQuery):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    org_id = callback.data[8:]
    await callback.message.answer("Спасибо!", reply_markup=std_kbd)
    # await callback.message.answer(f"Вы выбрали организацию: {org_id}")
    if org_id:
        my_iiko.set_organization(org_id)
    else:
        await callback.message.answer(f"Нет организации для работы!")
    await callback.answer()


@dp.message_handler(regexp=r"^\d+$", state=ClientStatesGroup.search_card)
async def get_by_card(message: types.Message, state: FSMContext) -> None:
    customer = my_iiko.get_customer_by_card(message.text)
    addition_info = ""
    ikb = None
    kbd = None
    try:
        name = f"ФИО пользователя: {customer['surname']} {customer['name'] if customer['name'] else ''}"
        await store_customer_data(state, customer)

        ikb = get_customer_kbd(customer['id'], message.from_user.id)

        await ClientStatesGroup.customer.set()
        kbd = usr_kbd
        addition_info = form_check_cats_and_progs(customer)  # f"Дополнительные команды:\n{ADDITION_ACTS}"

    except KeyError:
        name = f'По данному номеру карты {message.text} пользователь не найден!'
        ikb = await get_confirm_kbd('❓ Добавить пользователя?', 'add_cust_card', 'cancel')
        async with state.proxy() as data:
            data['card'] = message.text
        addition_info = "Или введите другой номер карты:"
    except Exception as err:
        name = f'Ошибка: {err}\nПопробуйте начать поиск сначала.'
        await state.finish()

    await message.reply(name, reply_markup=ikb)
    if addition_info:
        await message.answer(addition_info, reply_markup=kbd)


@dp.callback_query_handler(text='add_cust_card', state=ClientStatesGroup.search_card)
async def new_customer_by_card(callback: types.CallbackQuery, state: FSMContext):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    async with state.proxy() as data:
        card = data['card']
    await callback.message.answer(f"Чтобы продолжить, для карты № {card}"
                                  f"\nВведите трек номер:")
    await ClientStatesGroup.add_track.set()
    await callback.answer()


@dp.callback_query_handler(lambda callback: callback.data.startswith('cardsel_'), state=ClientStatesGroup.customer)
async def sel_card(callback: types.CallbackQuery):
    card_to_chg = callback.data[8:]
    ikb = None
    customer = my_iiko.get_customer_by_cardTrack(card_to_chg)
    out_data = f"""Вы действительно хотите изменить карту у пользователя:
    {customer['surname']} {customer['name'] if customer['name'] else ''} {customer['middleName'] if customer['middleName'] else ''}
    Дата рождения: {customer['birthday']}
    Телефон: {customer['phone']}
    E-Mail: {customer['email']}
    """
    for card in customer['cards']:
        if card['track'] == card_to_chg:
            ikb = await get_confirm_kbd(f"❌ Изменить {card['number']}", f"cardchg_{card['track']}", "cancel_soft", 2)
    await bot.edit_message_text(out_data, chat_id=callback.message.chat.id, message_id=callback.message.message_id)
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=ikb)


@dp.callback_query_handler(lambda callback: callback.data.startswith('cardchg_'), state=ClientStatesGroup.customer)
async def chg_card(callback: types.CallbackQuery, state: FSMContext):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    card_to_del = callback.data[8:]
    customer = my_iiko.get_customer_by_cardTrack(card_to_del)
    customer_id = customer['id']
    for card in customer['cards']:
        if card['track'] == card_to_del:
            card_no_to_del = card['number']

    async with state.proxy() as data:
        data['old_cardTrack'] = card_to_del
        data['old_card'] = card_no_to_del
        data['state'] = await state.get_state()
    await callback.message.answer('Введите новый номер карты пользователя:')
    await ClientStatesGroup.add_card.set()

    await callback.answer()
    # await state.finish()


@dp.callback_query_handler(lambda callback: callback.data.startswith('selcard_'), state=ClientStatesGroup.customer)
async def change_card(callback: types.CallbackQuery):
    customer_id = callback.data[8:]
    result = my_iiko.get_customer_by_id(customer_id)
    ikb = get_card_kbd(result['cards'])
    await callback.message.answer("Выберите карту для изменения.", reply_markup=ikb)
    await callback.answer()


@dp.callback_query_handler(lambda callback: callback.data.startswith('category_'), state=ClientStatesGroup.customer)
async def check_customer_category(callback: types.CallbackQuery, state: FSMContext) -> None:
    customer_id = callback.data[9:]
    result = my_iiko.get_customer_by_id(customer_id)
    await store_customer_data(state, result)
    ikb = types.InlineKeyboardMarkup(row_width=1)
    async with state.proxy() as data:
        customer_id = data['customer']
        customer = data['full_name']
        categories = data['categories']

    if categories:
        for cat in categories:
            ikb.add(types.InlineKeyboardButton(text=f"❌ {cat['name']}", callback_data=f"catdel_{cat['id']}"))

    # TODO нужна проверка на возможность добавления категории, чтобы кнопка
    #  "добавить категорию" не появлялась если больше нет их к добавлению.
    ikb.add(types.InlineKeyboardButton(text='✅ Добавить категорию', callback_data="addcat"))
    ikb.add(types.InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_soft"))
    await callback.message.answer(f" Выберите категории для {customer}", reply_markup=ikb)
    await callback.answer()


@dp.callback_query_handler(lambda callback: callback.data.startswith('wallets_'), state=ClientStatesGroup.customer)
async def check_customer_wallets(callback: types.CallbackQuery, state: FSMContext) -> None:
    customer_id = callback.data[8:]
    result = my_iiko.get_customer_by_id(customer_id)
    await store_customer_data(state, result)
    ikb = types.InlineKeyboardMarkup(row_width=1)
    async with state.proxy() as data:
        customer = data['full_name']
        wallets = data['wallets']

    if wallets:
        for wallet in wallets:
            ikb.add(types.InlineKeyboardButton(text=f"❌ {wallet['name']}", callback_data=f"fillwallet_{wallet['id']}"))
    ikb.add(types.InlineKeyboardButton(text='✅ Добавить кошелёк(программу)', callback_data="addwallet"))
    ikb.add(types.InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_soft"))
    await callback.message.answer(f" Выберите кошелёк для {customer}", reply_markup=ikb)
    await callback.answer()


@dp.callback_query_handler(text="addwallet", state=ClientStatesGroup.customer)
async def add_to_prog(callback: types.CallbackQuery, state: FSMContext):
    ikb = types.InlineKeyboardMarkup(row_width=1)
    async with state.proxy() as data:
        customer = data['full_name']
        try:
            wallets = {x['name'] for x in data['wallets']}
        except TypeError:
            wallets = {}
    all_progs = my_iiko.loyalty_programs()
    for prog in all_progs['Programs']:
        if prog['name'] not in wallets:
            if prog['isActive']:
                ikb.add(types.InlineKeyboardButton(text=f"✅ {prog['name']}", callback_data=f"progadd_{prog['id']}"))
    ikb.add(types.InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_soft"))
    await callback.message.edit_text(f" Добавьте пользователя {customer} в программу лояльности", reply_markup=ikb)


@dp.callback_query_handler(lambda callback: callback.data.startswith('progadd_'), state=ClientStatesGroup.customer)
async def add_prog(callback: types.CallbackQuery, state: FSMContext):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    prog_to_add = callback.data[8:]
    async with state.proxy() as data:
        customer_id = data['customer']
        customer = data['full_name']
    result = my_iiko.loyalty_select_program(customer_id, prog_to_add)
    try:
        wallet_id = result['userWalletId']
    except Exception as ex:
        wallet_id = None
        await callback.message.answer(f'Не получилось добавить в программу лояльности!\n'
                                      f'Возникла ошибка: {ex}')
        log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                                            f" Пользователь @{callback.from_user.username} НЕ СМОГ ДОБАВИТЬ"
                                            f" гостя {customer_id} в программу {prog_to_add} c результатом {result}")
    if wallet_id:
        log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                                            f" Пользователь @{callback.from_user.username} ДОБАВИЛ"
                                            f" гостя {customer_id} в программу {prog_to_add} c результатом {result}")
        await callback.message.answer(f"🟢 Пользователь {customer} добавлен в программу лояльности\n"
                                      f" Теперь у него есть кошелёк: {wallet_id}")
        await callback.answer("Кошелёк добавлен!")
    else:
        await callback.answer("Кошелёк не был сформирован!")


@dp.callback_query_handler(lambda callback: callback.data.startswith('modify_'), state=ClientStatesGroup.customer)
async def modify_customer(callback: types.CallbackQuery, state: FSMContext) -> None:
    # customer_id = callback.data[7:]
    # result = my_iiko.get_customer_by_id(customer_id)
    out_text = await form_customer_personal_data_from_state(state)
    ikb = modify_ikb
    await callback.message.answer(out_text, reply_markup=ikb)
    await callback.answer()


@dp.callback_query_handler(lambda callback: callback.data.startswith('change_'), state=ClientStatesGroup.customer)
async def change_customer_data1(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data[7:]
    async with state.proxy() as data:
        data['state'] = await state.get_state()  # сохраняем состояние
        name = data['full_name']
        if 'action' in data:
            return await callback.answer("Сначала закончите начатое действие!")
        else:
            data['action'] = action
        phone = data['phone']
        data['message_id'] = callback.message.message_id
        data['chat_id'] = callback.message.chat.id
    await callback.message.answer(
        f'Чтобы изменить <b>{MODIFY_ACTIONS[action]}</b> для пользователя {name}\n с телефоном {phone}:\n'
        f'Введите новое значение поля <b>{MODIFY_ACTIONS[action]}:</b>',
        parse_mode='HTML')
    await ClientStatesGroup.set_data.set()
    await callback.answer()


@dp.callback_query_handler(text='cancel_soft', state=ClientStatesGroup.customer)
async def cancel_soft(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        if 'action' in data:
            data.__delitem__('action')
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    await callback.answer('Отменено!')


@dp.message_handler(state=ClientStatesGroup.set_data)
async def change_customer_data2(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        action = data['action']
        field = data[action]
        if action == 'phone':
            if not re.match(PHONE_TEMPLATE, message.text):
                return await message.answer("Введите корректный номер телефона")
        await state.set_state(data['state'])  # Возвращаем предыдущее сохраненное состояние
        data[f"new_{data['action']}"] = message.text
    text = f'⚠️ {MODIFY_ACTIONS[action]}: {field}\n<b>Заменить на: {message.text}</b>'
    ikb = await get_confirm_kbd('✅ Подтвердить', 'new_name', 'cancel_soft', 2)
    await message.answer(text, reply_markup=ikb, parse_mode='HTML')


@dp.callback_query_handler(text='new_name', state=ClientStatesGroup.customer)
async def new_customer_data(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        customer_id = data['customer']
        if 'action' in data:
            action = data['action']
            name = data[f"new_{data['action']}"]
            value = data[action]
        else:
            return callback.answer('Действие невозможно в данной ситуации!')
        msg_id = data['message_id']
        chat = data['chat_id']
    payload = {
        "id": customer_id,
        action: name,
        "organizationId": my_iiko.organization_id
    }
    info = my_iiko.create_or_update_customer(payload)
    log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                                        f" Пользователь @{callback.from_user.username} ИЗМЕНИЛ {action},"
                                        f" гостю {customer_id} c '{value}' на '{name}' и получил результат {info}")
    customer = my_iiko.get_customer_by_id(customer_id)
    await store_customer_data(state, customer)
    out_data = f"🟢 {MODIFY_ACTIONS[action]} изменено на: {name}"

    await bot.edit_message_text(out_data, chat_id=callback.message.chat.id,
                                message_id=callback.message.message_id, reply_markup=None)
    async with state.proxy() as data:
        data.__delitem__('action')
    new_data = await form_customer_personal_data_from_state(state)
    await bot.edit_message_text(new_data, chat_id=chat,
                                message_id=msg_id, reply_markup=modify_ikb)

    await callback.answer("Изменено!")


@dp.callback_query_handler(text="addcat", state=ClientStatesGroup.customer)
async def add_cat(callback: types.CallbackQuery, state: FSMContext):
    ikb = types.InlineKeyboardMarkup(row_width=1)
    async with state.proxy() as data:
        customer = data['full_name']
        try:
            categories = {x['id'] for x in data['categories']}
        except TypeError:
            categories = {}
    all_cats = my_iiko.loyalty_categories()
    for cat in all_cats['guestCategories']:
        if cat['id'] not in categories:
            if cat['isActive']:
                ikb.add(types.InlineKeyboardButton(text=f"✅ {cat['name']}", callback_data=f"catadd_{cat['id']}"))
    ikb.add(types.InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_soft"))
    await callback.message.edit_text(f" Добавьте категории пользователю {customer}", reply_markup=ikb)


@dp.callback_query_handler(lambda callback: callback.data.startswith('catdel_'), state=ClientStatesGroup.customer)
async def del_cat(callback: types.CallbackQuery, state: FSMContext):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    cat_to_del = callback.data[7:]
    async with state.proxy() as data:
        customer_id = data['customer']
        customer = data['full_name']
        categories = data['categories']
    for cat in categories:
        if cat['id'] == cat_to_del:
            cat_name = cat['name']
    result = my_iiko.loyalty_remove_category(customer_id, cat_to_del)
    log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} "
                                        f"Пользователь @{callback.from_user.username} УДАЛИЛ категорию {cat_to_del},"
                                        f" гостя {customer_id} c результатом {result}")
    await callback.message.answer(f"🟢 Категория {cat_name} для {customer} удалена!\n")
    await callback.answer("Категория удалена!")
    # await state.finish()


@dp.callback_query_handler(lambda callback: callback.data.startswith('catadd_'), state=ClientStatesGroup.customer)
async def add_cat(callback: types.CallbackQuery, state: FSMContext):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    cat_to_add = callback.data[7:]
    async with state.proxy() as data:
        customer_id = data['customer']
        customer = data['full_name']
    categories = my_iiko.loyalty_categories()
    for cat in categories['guestCategories']:
        if cat['id'] == cat_to_add:
            cat_name = cat['name']
    result = my_iiko.loyalty_select_category(customer_id, cat_to_add)
    log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                                        f" Пользователь @{callback.from_user.username} ДОБАВИЛ категорию {cat_to_add},"
                                        f" гостю {customer_id} c результатом {result}")
    await callback.message.answer(f"🟢 Категория {cat_name} для {customer} добавлена!\n")
    await callback.answer("Категория добавлена.")
    # await state.finish()


@dp.callback_query_handler(text="addcard", state=ClientStatesGroup.customer)
async def ask_card1(callback: types.CallbackQuery):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    await callback.message.answer('Добавьте номер карты пользователю:')
    await ClientStatesGroup.add_card.set()
    await callback.answer()


@dp.message_handler(regexp=r"^\d+$", state=ClientStatesGroup.add_card)
async def add_card(message: types.Message, state: FSMContext) -> None:
    async with state.proxy() as data:
        try:
            customer = f"пользователю {data['full_name']}"
        except KeyError:
            customer = "новому пользователю."
        data['card'] = message.text
    await message.answer(f"Добавьте трек для карты № {message.text} {customer}\nВведите трек для карты:")
    await ClientStatesGroup.add_track.set()


@dp.message_handler(regexp=TRACK_TEMPLATE, state=ClientStatesGroup.add_track)
async def add_track(message: types.Message, state: FSMContext) -> None:
    change = False
    async with state.proxy() as data:
        try:
            customer_id = data['customer']
            customer = data['full_name']
        except KeyError:
            customer_id = None
            customer = ""
        card = data['card']
        data['cardTrack'] = message.text
        if 'old_cardTrack' in data:
            card_to_del = data['old_cardTrack']
            change = True
        if 'state' in data:
            return_state = data['state']
        else:
            return_state = ClientStatesGroup.customer
    if customer_id:
        result = my_iiko.loyalty_add_card(customer_id, message.text, card)
        if result == {}:
            await message.answer(f"🟢 Добавлена карта {card} с треком {message.text} для пользователя {customer}\n")
            log.getLogger('iiko-requests').info(
                f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} Пользователь @{message.from_user.username} ДОБАВИЛ карту {card}, гостю {customer_id}")
        else:
            await message.answer(f"Возникла ошибка добавления {result}")
            log.getLogger('iiko-requests').info(
                f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} Пользователь @{message.from_user.username} НЕ СМОГ ДОБАВИТЬ карту {card}, гостю {customer_id} c результатом {result}")
            await state.set_state(return_state)
            return
        if change:
            result = my_iiko.loyalty_delete_card(customer_id, card_to_del)
            if result == {}:
                log.getLogger('iiko-requests').info(
                    f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                    f" Пользователь @{message.from_user.username} УДАЛИЛ карту {card_to_del},"
                    f" гостя {customer_id}")
                await message.answer(f"🟢 Карта c треком {card_to_del} для {customer} удалена!\n")
            else:
                log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                                                    f" Пользователь @{message.from_user.username} НЕ СМОГ УДАЛИТЬ карту {card_to_del},"
                                                    f" гостя {customer_id} c результатом {result}")
                await message.answer(f"Не получилось удалить карту: {result}")
            await state.set_state(return_state)
            return
        await state.finish()
    else:
        result = my_iiko.get_customer_by_cardTrack(message.text)
        try:
            customer_id = result['id']
            await store_customer_data(state, result)
            await ClientStatesGroup.customer.set()
            ikb = get_card_kbd(result['cards'])
            await message.reply(f"Указанный трек-номер закреплён за пользователем {result['surname']} {result['name']}",
                                reply_markup=ikb)
            log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                                                f" У Пользователя @{message.from_user.username} возник КОНФЛИКТ при заведении карты {card}"
                                                f", гостю {customer_id} c результатом {result}")
        except KeyError:
            print(result['message'])
            await message.answer(f"Не установлен пользователь для карты № {card}\nС треком: {message.text}\n")
            await message.answer(f"Если хотите завести нового пользователя - введите его ФИО:")
            await ClientStatesGroup.add_custom_name.set()


@dp.message_handler(regexp=r"^[^\/].*$", state=ClientStatesGroup.add_custom_surname)
async def ask_surname(message: types.Message, state: FSMContext) -> None:
    async with state.proxy() as data:
        data['surname'] = message.text
    await message.answer('Теперь введите Имя пользователя:')
    await ClientStatesGroup.add_custom_name.set()


@dp.message_handler(regexp=r"^[^\/].*$", state=ClientStatesGroup.add_custom_name)
async def create_new_customer(message: types.Message, state: FSMContext):
    surname = message.text
    async with state.proxy() as data:
        data['surname'] = surname
        card = data['card']
        cardTrack = data['cardTrack']
    ikb = await get_confirm_kbd('✅ Добавить', 'add_new_customer', 'cancel', 2)
    await message.answer(f"⚠️ ВНИМАТЕЛЬНО проверьте данные:\n"
                         f"Пользователь: {surname}\n"
                         f"Карточка № {card} с треком {cardTrack}.\n"
                         f"Будет добавлен в систему!", reply_markup=ikb)


@dp.callback_query_handler(text='add_new_customer', state=ClientStatesGroup.add_custom_name)
async def add_new_customer(callback: types.CallbackQuery, state: FSMContext):
    async with state.proxy() as data:
        surname = data['surname']
        card = data['card']
        cardTrack = data['cardTrack']

    payload = {
        "surname": surname,
        "cardTrack": cardTrack,
        "cardNumber": card,
        "organizationId": my_iiko.organization_id
    }
    info = my_iiko.create_or_update_customer(payload)
    print(info)
    if 'id' in info:
        log.getLogger('iiko-requests').info(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}"
                                            f" Пользователь @{callback.from_user.username} ЗАВЁЛ КАРТОЧКУ "
                                            f" гостя {surname} с № {card}, треком {cardTrack} и получил результат {info}")
        card_result = f"Карточка № {card} с треком {cardTrack}.\n"
        customer = my_iiko.get_customer_by_id(info['id'])
        await store_customer_data(state, customer)
        await ClientStatesGroup.customer.set()
        ikb = get_customer_kbd(customer['id'], callback.from_user.id)  # get_card_kbd(customer['cards'])
        addition_info = form_check_cats_and_progs(customer)
        await bot.edit_message_text(f"Пользователь: {surname}\n"
                                    f"{card_result}"
                                    f"Был добавлен в систему!\n" + addition_info, chat_id=callback.message.chat.id,
                                    message_id=callback.message.message_id, reply_markup=ikb)
        await callback.answer("Добавлено!")
    else:
        log.getLogger('iiko-requests').info(f"ошибка добавления - {info}")
        await callback.answer("ОШИБКА! Пользователь НЕ добавлен!")


@dp.message_handler(state=ClientStatesGroup.add_card)
@dp.message_handler(state=ClientStatesGroup.search_card)
async def check_input(message: types.Message, state: FSMContext) -> None:
    if message.text == '/cancel':
        await cancel_command(message, state)
    else:
        status_type = str(await state.get_state())
        if status_type.endswith('_card'):
            await message.reply(f'Введите корректный номер карты или /cancel - для отмены.')
        else:
            await message.reply('Некорректный ввод!')


@dp.message_handler(state=ClientStatesGroup.add_track)
async def check_track(message: types.Message) -> None:
    await message.answer('Трек введён не корректно!\nВведите корректный номер трека:')


@dp.callback_query_handler(lambda callback: callback.data.startswith('olaps_'), state='*')
async def select_olap_card(callback: types.CallbackQuery, state: FSMContext):
    customer_id = callback.data[6:]
    result = my_iiko.get_customer_by_id(customer_id)
    await callback.message.answer('Выберете карту для отчёта', reply_markup=get_olaps_kbd(result['cards']))
    await callback.answer()


@dp.callback_query_handler(lambda callback: callback.data.startswith('getolap_'), state='*')
async def get_start_date(callback: types.CallbackQuery, state: FSMContext):
    card_number = callback.data[8:]
    async with state.proxy() as data:
        data['card_number'] = card_number
        data['state'] = await state.get_state()
    await callback.message.answer(f'Введите начало периода для карты {card_number} в формате день.месяц.ГОД')
    await ClientStatesGroup.select_date_start.set()
    await callback.answer()


@dp.message_handler(state=ClientStatesGroup.select_date_start)
async def get_end_date(msg: types.Message, state: FSMContext):
    pattern = re.compile(r"^(0[1-9]|[12][0-9]|3[01])[.](0[1-9]|1[1,2])[.]20\d{2}$")
    if not pattern.match(msg.text):
        if msg.text == '/cancel':
            async with state.proxy() as data:
                if 'card_number' in data:
                    data.__delitem__('card_number')
                if 'state' in data:
                    return_state = data['state']
                    data.__delitem__('state')
                else:
                    return_state = ClientStatesGroup.customer
            await state.set_state(return_state)
        else:
            await msg.answer('❌ Введите корректную дату начала периода!\nНапример 23.11.2022')
        return
    async with state.proxy() as data:
        card = data['card_number']
        data['olap_start_date'] = msg.text
    await msg.answer(f"Теперь введите конечную дату для карты {card} с началом периода {msg.text} в формате день.месяц.ГОД")
    await ClientStatesGroup.select_date_end.set()


@dp.message_handler(state=ClientStatesGroup.select_date_end)
async def get_olap(msg: types.Message, state: FSMContext):
    async with state.proxy() as data:
        if 'answer' in data:
            answer = data['answer']
        else:
            answer = None
        card = data['card_number']
        start = data['olap_start_date']
    if answer:  # если не терпеливый пользователь написал ещё сообщение, во время процесса обработки
        await msg.delete()
        await msg.answer('Необходимо дождаться окончания загрузки!')
        return
    pattern = re.compile(r"^(0[1-9]|[12][0-9]|3[01])[.](0[1-9]|1[0-2])[.]20\d{2}$")
    if not pattern.match(msg.text):
        if msg.text == '/cancel':
            async with state.proxy() as data:
                if 'card_number' in data:
                    data.__delitem__('card_number')
                if 'olap_start_date' in data:
                    data.__delitem__('olap_start_date')
                if 'state' in data:
                    return_state = data['state']
                    data.__delitem__('state')
                else:
                    return_state = ClientStatesGroup.customer
            await state.set_state(return_state)
        else:
            await msg.answer('❌ Введите корректную дату окончания периода!\nНапример 24.11.2022')
        return
    answer = await msg.answer(f'Выбрана карта {card}. За период с {start} по {msg.text}.')
    print(f"{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')} пользователь {msg.from_user.username}"
          f" запросил отчёт по карте {card} за период с {start} по {msg.text}")
    start_date = datetime.strptime(start, "%d.%m.%Y")
    end_date = datetime.strptime(msg.text, "%d.%m.%Y")
    if end_date - start_date > timedelta(days=31):
        await msg.answer("Максимальный период для отчёта - 31 день.\n"
                         "Введите меньший диапазон или отмените действие через /cancel")
        return
    a = 0
    # await state.update_data(answer=answer)
    with concurrent.futures.ThreadPoolExecutor(1, 'load_olap_data') as executor:
        future = executor.submit(get_olap_data, card, start_date, end_date)
        while not future.done():
            await answer.edit_text(f"{answer.text}\n Загружаем данные... {a} сек.\n Ждите!")
            await sleep(1)
            a += 1
        raw_result = future.result()
    result = chunk_data_by_field(raw_result.sort_values(by=['Время закрытия']), 'Время закрытия')
    if result:
        for res in result:
            out_string = f"🕰{res.iat[0,0]} 📃 {res.iat[0,1]} 🏦 {res.iat[0,2]}\n"
            for i, row in res.iterrows():
                out_string += f"""🍛 {row['Блюдо']} ({row['Количество блюд']}) 💰 {row['Сумма без скидки']} руб.\n"""
            await msg.answer(f"{out_string}")
    else:
        await msg.answer(f"За данный период у пользователя карточки {card} записей не найдено!")
    async with state.proxy() as data:
        if 'answer' in data:
            data.__delitem__('answer')
        if 'state' in data:
            return_state = data['state']
            data.__delitem__('state')
        else:
            return_state = ClientStatesGroup.customer
    await state.set_state(return_state)


@dp.callback_query_handler(text='cancel_del', state=ClientStatesGroup.customer)
async def cancel_del(callback: types.CallbackQuery, state: FSMContext):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    await callback.message.answer('Отменено! Начните сначала', reply_markup=std_kbd)
    await callback.answer('Действие отменено!')
    await state.finish()


@dp.message_handler(commands=['cancel'], state='*')
async def cancel_command(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer('Отменено!')
    await connect(message, my_iiko)


@dp.callback_query_handler(text='cancel', state='*')
async def cmd_cancel(callback: types.CallbackQuery, state: FSMContext):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    await state.finish()
    await callback.message.answer('Действие отменено! Начните сначала.')
    await callback.answer("Отменено!")


@dp.message_handler(state=ClientStatesGroup.customer)
async def check_other_customer(message: types.Message, state: FSMContext) -> None:
    async with state.proxy() as data:
        customer = data['full_name']
        customer_id = data['customer']
    await message.answer(f"Я ожидаю ваших действий по пользователю: {customer}",
                         reply_markup=get_customer_kbd(customer_id, message.from_user.id))


@dp.callback_query_handler(state='*')
async def incorrect(callback: types.CallbackQuery):
    await bot.edit_message_reply_markup(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        reply_markup=None)
    await callback.answer('Некорректное действие или оно уже потеряло актуальность!')


@dp.message_handler(state='*')
async def check_other(message: types.Message) -> None:
    await message.answer('Введите /help для помощи или выберете действие: /card', reply_markup=std_kbd)

# ------>>>>> Начало основной программы

if __name__ == '__main__':
    log.basicConfig(level=log.INFO,
                    format="%(asctime)s - [%(levelname)s] - %(name)s - "
                           "(%(filename)s).%(funcName)s(%(lineno)d) - %(message)s")  # , filename='log.txt', encoding='utf-8')

    log.getLogger('iiko-requests').addHandler(log.FileHandler('iiko.log'))
    # log.addLevelName()

    dp.middleware.setup(CheckMiddleware())

    if WEBHOOK:
        app.on_startup.append(on_startup)
        app.on_shutdown.append(on_shutdown)
        web.run_app(app, host='0.0.0.0', port=8443)
    else:
        executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown, skip_updates=True,
                               allowed_updates=["message", "callback_query"], timeout=250, relax=0.5)
