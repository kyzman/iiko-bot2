import unittest
from iiko import IikoCardAPI
from config import apiLogin, TARDAN_Login, TAISHET_Login
import pprint

class TestIikoAPI_1(unittest.TestCase):
    api1 = IikoCardAPI(TARDAN_Login)  # регистрация класса который будет использован в тестах
    token = api1.set_token()  # получение токена
    orgs: list = api1.organizations(True)['organizations']
    if orgs:  # проверка наличия хотя-бы одной записи в списке
        organizationid = orgs[0]['id']  # выбор самой первой организации с которой будем работать
        api1.set_organization(organizationid)  # установка организации по умолчанию в классе для тестов
    else:
        raise ValueError(f'Нет организаций для выбора. Список организаций пуст!')

    def test_get_orgs(self) -> None:
        """ Проверка выдачи организаций"""
        result = self.api1.get_service_organization()
        pprint.pp(result)
        self.assertIsNotNone(result)

    def test_get_terms(self) -> None:
        """ Проверка выдачи терминалов"""
        result = self.api1.get_terminal_groups(includeDisabled=True)
        pprint.pp(result)
        self.assertIsNotNone(result)

    def test_loyalty_prg(self) -> None:
        """ Проверка выдачи программ лояльности"""
        print(self.api1.organization_id)
        lps = self.api1.loyalty_programs()
        for lp in lps['Programs']:
            if lp['isActive']:
                print('[·] - ', lp['name'])
        pprint.pprint(lps)
        self.assertIsNotNone(lps['Programs'])

    def test_get_categories(self) -> None:
        """ Проверка выдачи категорий программы лояльности"""
        lcs = self.api1.loyalty_categories()
        for lc in lcs['guestCategories']:
            if lc['isActive']:
                print('[·] - ', lc['name'])
        pprint.pprint(lcs)
        self.assertIsNotNone(lcs['guestCategories'])
