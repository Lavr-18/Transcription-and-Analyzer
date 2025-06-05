import os
import json
import requests
from datetime import datetime


FORM_URL = "https://docs.google.com/forms/u/0/d/e/1FAIpQLSeI-BvmkSZgzGXeQB83KQLR0O-5_ALgdhWg9LoMV7DskLqBLQ/formResponse"

ENTRY_MAP = {
    "number": "entry.1684791713",
    "name": "entry.730205749",
    "phone": "entry.1794131010",
    "date": "entry.887244152",
    "улыбка_в_голосе": "entry.762756437",
    "установление_контакта": "entry.2128803646",
    "квалификация": "entry.1587001077",
    "выявление_потребности": "entry.298145485",
    "пересогласование": "entry.1475320463",
    "особенности_позиций": "entry.427767033",
    "возражение": "entry.374927679",
    "отработка_возражения": "entry.1984762538",
    "докомплект": "entry.1050706243",
    "допродажа": "entry.866877333",
    "состав_и_сумма": "entry.1544107090",
    "согласование_деталей": "entry.1922686497",
    "предоплата": "entry.257021647"
}


def send_analyses_to_google_form(folder_path):
    today_str = datetime.today().strftime("%d.%m.%Y")
    counter = 1

    for filename in sorted(os.listdir(folder_path)):
        if not filename.endswith("_analysis.json"):
            continue

        file_path = os.path.join(folder_path, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ПРИМЕЧАНИЕ: заменить на реальные имя и номер, если есть
        name = "Имя"
        phone = "Номер"

        payload = {
            ENTRY_MAP["number"]: counter,
            ENTRY_MAP["name"]: name,
            ENTRY_MAP["phone"]: phone,
            ENTRY_MAP["date"]: today_str,
        }

        for key in data:
            if key in ENTRY_MAP:
                payload[ENTRY_MAP[key]] = data[key]

        response = requests.post(FORM_URL, data=payload)
        if response.status_code == 200:
            print(f"[✓] Отправлено: {filename}")
        else:
            print(f"[✗] Ошибка: {filename} — Status {response.status_code}")

        counter += 1
