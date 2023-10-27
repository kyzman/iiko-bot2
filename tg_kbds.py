from aiogram import types
from tg_const import ADMIN_IDs


def get_admin(user_id) -> bool:
    return user_id in ADMIN_IDs



std_kbd = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton('/card')
                                                              ).add(types.KeyboardButton('/cancel'))

usr_kbd = types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton('/cancel'))

modify_ikb = types.InlineKeyboardMarkup(row_width=1).add(types.InlineKeyboardButton(
    text='📙 Изменить Фамилию', callback_data="change_surname")).add(types.InlineKeyboardButton(
    text='📘 Изменить Имя', callback_data="change_name")).add(types.InlineKeyboardButton(
    text='📗 Изменить Отчество', callback_data="change_middleName")).add(types.InlineKeyboardButton(
    text='☎️ Изменить Телефон', callback_data="change_phone")).add(types.InlineKeyboardButton(
    text="🚫 Отменить", callback_data="cancel_soft"))


async def get_confirm_kbd(submit_text: str, submit_data: str, cancel_data: str,
                          rows: int = 1) -> types.InlineKeyboardMarkup:
    ikb = types.InlineKeyboardMarkup(row_width=rows)
    ikb.insert(types.InlineKeyboardButton(text=submit_text, callback_data=submit_data))
    ikb.insert(types.InlineKeyboardButton(text="🚫 Отменить", callback_data=cancel_data))
    return ikb


def get_card_kbd(cards=None) -> types.InlineKeyboardMarkup:
    ikb = types.InlineKeyboardMarkup(row_width=1)
    if cards:
        for card in cards:
            ikb.add(
                types.InlineKeyboardButton(text=f"❌ {card['number']}", callback_data=f"cardsel_{card['track']}"))
    else:
        ikb.add(types.InlineKeyboardButton(text='✅ Добавить карту', callback_data="addcard"))
    ikb.add(types.InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_soft"))
    return ikb


def get_olaps_kbd(cards=None) -> types.InlineKeyboardMarkup:
    ikb = types.InlineKeyboardMarkup(row_width=1)
    if cards:
        for card in cards:
            ikb.add(
                types.InlineKeyboardButton(text=f"✅ {card['number']}", callback_data=f"getolap_{card['number']}"))
    else:
        pass
    ikb.add(types.InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_soft"))
    return ikb


def get_customer_kbd(user_id, request_id=None) -> types.InlineKeyboardMarkup:
    ikb = types.InlineKeyboardMarkup(row_width=1)
    ikb.add(types.InlineKeyboardButton(text="Отчёт по расходам карты", callback_data=f"olaps_{user_id}"))
    ikb.add(types.InlineKeyboardButton(text="Категории пользователя", callback_data=f"category_{user_id}"))
    ikb.add(types.InlineKeyboardButton(text="Карты пользователя", callback_data=f"selcard_{user_id}"))
    ikb.add(types.InlineKeyboardButton(text="Кошельки и программы пользователя", callback_data=f"wallets_{user_id}"))
    if get_admin(request_id):
        ikb.add(types.InlineKeyboardButton(text="Персональные данные", callback_data=f"modify_{user_id}"))
    ikb.add(types.InlineKeyboardButton(text="🚫 Отменить", callback_data="cancel_del"))
    return ikb
