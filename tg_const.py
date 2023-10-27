
# вывод информации для пользователя в разных ситуациях
HELP_COMMAND = """
<b>/help</b><em> - помощь</em>
<b>/start</b><em> - Начать работу(аналогично /card)</em>
<b>/card</b><em> - Получить информацию о сотруднике по номеру карты или создать, если карта не найдена.</em>
<b>/cancel</b><em> - Отменить все действия и переподключиться.(в любой непонятной ситуации, если что-то не работает или работает не так как вы ожидаете, выберете это).
                    </em>
"""

ADDITION_ACTS = "/balance - посмотреть баланс пользователя\n" \
                "/setcat - установить категорию\n" \
                "/modify - изменить данные пользователя"

# шаблоны для проверки ввода данных пользователя
PHONE_TEMPLATE = r"^((8|\+7)[\- ]?)?(\(?\d{3}\)?[\- ]?)?[\d\- ]{7,10}$"  # шаблон соответствия формату номеру телефона
TRACK_TEMPLATE = r"^\d+=*\d+$"  # шаблон соответствия треку карты

# шаблоны соответствия названий полям в БД Iiko
MODIFY_ACTIONS = {"phone": "Телефон", "name": "Имя", "middleName": "Отчество", "surname": "Фамилия", }

# правила безопасности работы с ботом
ALLOWED_IDs = {5027774009,
               589869224,
               1479781418,
               }  # Список telegram ID пользователей, кому будет разрешено взаимодействие с ботом.

ADMIN_IDs = {5027774009,
             589869224,
}   # список telegram ID пользователей, которые имеют ADMIN права взаимодействия с ботом.

