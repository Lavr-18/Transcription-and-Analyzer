import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

# URL вашей Google Forms
FORM_URL = "https://docs.google.com/forms/u/0/d/e/1FAIpQLSeI-BvmkSZgzGXeQB83KQLR0O-5_ALgdhWg9LoMV7DskLqBLQ/formResponse"

# Соответствие полей анализа и названий полей в Google Forms
ENTRY_MAP = {
    "number": "entry.1684791713",
    "name": "entry.730205749",
    "phone": "entry.1794131010",
    "дата_звонка": "entry.887244152",
    "тип_звонка": "entry.1308973478",
    "ссылка_заказ": "entry.1438937468",
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

# Расширения для менеджеров
EXTENSIONS = {
    "Анастасия": "35",
    "Вера": "45",
    "Амалия": "33",
    "Евгения": "39",
    "Антон": "47",
    "Ангелина": "40",
    "Виктория": "41",
    "Александр": "42",
    "Екатерина": "46"
}


def send_analyses_to_google_form(folder_path):
    """
    Отправляет данные анализа звонков в Google Forms.
    """
    counter = 1  # Счетчик для номера звонка

    # Получаем вчерашнюю дату, чтобы сформировать путь к папке audio
    yesterday_date_str = (datetime.now().astimezone() - timedelta(days=1)).strftime("%d.%m.%Y")
    # Базовая папка для аудиофайлов (там, где находятся _call_info.json)
    audio_calls_folder = Path("audio") / f"звонки_{yesterday_date_str}"

    # Итерируем по всем JSON-файлам анализа в указанной папке
    for filename in sorted(os.listdir(folder_path)):
        if not filename.endswith("_analysis.json"):
            continue

        # Извлекаем базовое имя файла (например, "call1", "call2")
        base_name = filename.replace("_analysis.json", "")
        analysis_path = os.path.join(folder_path, filename)

        # Формируем правильный путь к соответствующему файлу информации о звонке
        # Теперь ищем его в папке audio/звонки_дд.мм.гггг/
        info_path = audio_calls_folder / f"{base_name}_call_info.json"

        # Загружаем данные анализа
        with open(analysis_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Инициализируем start_time и call_type значениями по умолчанию
        start_time = ""
        call_type = ""  # Инициализация для типа звонка

        # Загружаем информацию о звонке, если файл найден
        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    call_info = json.load(f)

                # Извлекаем 'start_time'
                start_time = call_info.get("start_time", "")

                # Извлекаем 'direction' из 'raw' и преобразуем в "Входящий" или "Исходящий"
                direction = call_info.get("raw", {}).get("direction", "")
                if direction == "in":
                    call_type = "Входящий"
                elif direction == "out":
                    call_type = "Исходящий"
                # Если direction не "in" и не "out", call_type останется пустым
            except json.JSONDecodeError as e:
                print(f"Ошибка декодирования JSON для {info_path}: {e}")
            except Exception as e:
                print(f"Ошибка при чтении или обработке {info_path}: {e}")
        else:
            print(f"Предупреждение: Файл информации о звонке не найден для {base_name}: {info_path}")

        # Определяем имя менеджера
        manager = data.get("manager_name", "Имя")

        # Формируем номер телефона с добавочным, если менеджер известен
        phone_base = "74950855397"
        extension = EXTENSIONS.get(manager)
        phone = f"{phone_base} доб. {extension}" if extension else phone_base

        # Формируем payload (набор данных) для отправки в Google Forms
        payload = {
            ENTRY_MAP["number"]: counter,
            ENTRY_MAP["name"]: manager,
            ENTRY_MAP["phone"]: phone,
            ENTRY_MAP["дата_звонка"]: start_time,
            ENTRY_MAP["тип_звонка"]: call_type  # Добавляем тип звонка
        }

        # Добавляем остальные критерии анализа в payload
        for key in data:
            # Имя и тип звонка уже обработаны отдельно
            if key in ENTRY_MAP and key not in ["name", "тип_звонка"]:
                payload[ENTRY_MAP[key]] = data[key]

        # Отправляем данные в Google Forms
        response = requests.post(FORM_URL, data=payload)
        if response.status_code == 200:
            print(f"[✓] Отправлено: {filename}")
        else:
            print(f"[✗] Ошибка: {filename} — Status {response.status_code}. Ответ: {response.text}")

        counter += 1  # Увеличиваем счетчик для следующего звонка
