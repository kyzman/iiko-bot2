from time import sleep

import requests
import pandas as pd
from lxml import etree
from datetime import datetime, timedelta
from pympler import asizeof
import concurrent.futures
from config import OLAP_login, OLAP_pwd

def human_format(num):
    num = float('{:.3g}'.format(num))
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '{}{}'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])


def get_intervals_by_day(start_date: datetime, end_date: datetime, day_interval: int ) -> list:
    new_list = []
    res_list = []
    date_list = [start_date]
    t_delta = (end_date - start_date).days
    pos = 0
    while t_delta >= day_interval:
        date_list.append(date_list[pos] + timedelta(days=day_interval))
        new_list.append(date_list[-1] - timedelta(days=1))
        res_list.append({'start': date_list[-2], 'end': new_list[-1]})
        t_delta -= day_interval
        pos += 1
    res_list.append({'start': date_list[-1], 'end': end_date})
    date_list.append(end_date)
    return res_list


def chunk_data(data: pd.DataFrame, lines=10) -> list[pd.DataFrame]:
    pos = 0
    end_pos = len(data)
    new_data = []
    while pos < end_pos:
        new_data.append(data.iloc[pos:pos+lines])
        pos += lines
    return new_data


def chink_data_by_field(data: pd.DataFrame, field) -> list[pd.DataFrame]:
    stamps = sorted(list(set(data[field])))
    out_data = []
    for stamp in stamps:
        out_data.append(data[data[field] == stamp])
    return out_data


def get_olap_html(card, start_date, end_date) -> pd.DataFrame:
    start = datetime.now()
    session = requests.Session()

    payload = {'j_username': OLAP_login, 'j_password': OLAP_pwd}
    session.post('https://forvard-co.iiko.it/resto/j_spring_security_check', data=payload)
    transform = etree.XSLT(
        etree.fromstring(session.get('https://forvard-co.iiko.it/resto/service/reports/report-view.xslt').text))
    # report = session.post(
    #     f'https://forvard-co.iiko.it/resto/service/reports/report.jspx?dateFrom={start_date.strftime("%d.%m.%Y")}&dateTo={end_date.strftime("%d.%m.%Y")}&presetId=c902622a-3006-4744-a562-ba1e562445cc').text
    with open('buffer.out', 'r') as f:
        report = f.read()
    newdom = transform(etree.fromstring(report))
    print(f"web load - {(datetime.now() - start).seconds} сек")
    print(f"Size of report: {human_format(asizeof.asizeof(report))}")
    session.close()

    start = datetime.now()
    data = pd.read_html(etree.tostring(newdom), converters={'Номер карты клиента': str})[0]
    print(f"load to pandas - {(datetime.now() - start).seconds} сек")
    print(f"Size of pandas data: {human_format(asizeof.asizeof(data))}")
    return data[data['Номер карты клиента'] == card][
        ['Время закрытия', 'Номер чека', 'Группа', 'Блюдо', 'Количество блюд', 'Сумма без скидки']]


start_date = datetime.strptime('01.09.2023', "%d.%m.%Y")
end_date = datetime.strptime('30.09.2023', "%d.%m.%Y")


if __name__ == '__main__':
    print(get_intervals_by_day(start_date, end_date, 3))
    a = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(get_olap_html, '030657', start_date, end_date)
        while not future.done():
            print(f"running... {a} sec. ")
            sleep(1)
            a += 1
        result = future.result()

    print(result.to_markdown())


    # split = chunk_data(result,6)
    split = chink_data_by_field(result, 'Время закрытия')
    for s in split:
        print(s)
