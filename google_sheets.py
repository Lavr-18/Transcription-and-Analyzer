import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
import re
from telegram_bot_integration import send_telegram_message

# URL вашей Google Forms
FORM_URL = "https://docs.google.com/forms/u/0/d/e/1FAIpQLSeI-BvmkSZgzGXeQB83KQLR0O-5_ALgdhWg9LoMV7DskLqBLQ/formResponse"

# Соответствие полей анализа и названий полей в Google Forms
ENTRY_MAP = {
    "number": "entry.1684791713",
    "name": "entry.730205749",
    "phone": "entry.1794131010",
    "дата_звонка": "entry.887244152",
    "тип_звонка": "entry.1308973478",
    "ссылка_клиента": "entry.1438937468",  # Изменено: теперь это ссылка на карточку клиента
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

# Расширения для менеджеров (больше не используются для поля 'phone', но оставлены, если нужны в другом месте)
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


def get_call_number_from_filename(filename: str) -> int:
    """
    Извлекает числовой идентификатор звонка из имени файла.
    Например, для 'call12_analysis.json' вернет 12.
    """
    match = re.match(r'call(\d+)_analysis\.json', filename)
    if match:
        return int(match.group(1))
    return 0


def send_analyses_to_google_form(folder_path):
    """
    Отправляет данные анализа звонков в Google Forms и краткое резюме в Telegram,
    учитывая категорию звонка.
    """
    counter = 1

    yesterday_date_str = (datetime.now().astimezone() - timedelta(days=1)).strftime("%d.%m.%Y")
    audio_calls_folder = Path("audio") / f"звонки_{yesterday_date_str}"

    analysis_files = []
    for filename in os.listdir(folder_path):
        if filename.endswith("_analysis.json"):
            analysis_files.append(filename)

    analysis_files.sort(key=get_call_number_from_filename)

    for filename in analysis_files:
        base_name = filename.replace("_analysis.json", "")
        analysis_path = os.path.join(folder_path, filename)
        info_path = audio_calls_folder / f"{base_name}_call_info.json"

        call_summary = ""
        analysis_data = {}
        call_category = "Неизвестно"  # Инициализация категории

        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                analysis_data = json.load(f)
                call_summary = analysis_data.get("summary", "")
                call_category = analysis_data.get("call_category", "Неизвестно")  # Извлекаем категорию
        except FileNotFoundError:
            print(f"Предупреждение: Файл анализа не найден для {base_name}: {analysis_path}. Пропуск.")
            counter += 1
            continue
        except json.JSONDecodeError as e:
            print(f"Ошибка декодирования JSON для {analysis_path}: {e}. Пропуск.")
            counter += 1
            continue
        except Exception as e:
            print(f"Ошибка при чтении или обработке {analysis_path}: {e}. Пропуск.")
            counter += 1
            continue

        start_time = ""
        call_type = ""
        customer_card_link = ""  # Изменено с order_link на customer_card_link
        contact_phone_number = ""

        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    call_info = json.load(f)

                start_time = call_info.get("start_time", "")

                direction = call_info.get("raw", {}).get("direction", "")
                if direction == "in":
                    call_type = "Входящий"
                elif direction == "out":
                    call_type = "Исходящий"

                # Изменено: Извлекаем ссылку на карточку клиента
                customer_card_link = call_info.get("customer_card_link", "")

                contact_phone_number = call_info.get("contact_phone_number", "")
                if not contact_phone_number:
                    contact_phone_number = call_info.get("raw", {}).get("contact_phone_number", "")

            except json.JSONDecodeError as e:
                print(f"Ошибка декодирования JSON для {info_path}: {e}")
            except Exception as e:
                print(f"Ошибка при чтении или обработке {info_path}: {e}")
        else:
            print(f"Предупреждение: Файл информации о звонке не найден для {base_name}: {info_path}")

        manager = analysis_data.get("manager_name", "Имя")
        phone_to_send = contact_phone_number

        # --- Логика отправки в Google Forms ---
        if call_category == "Заказ":
            payload = {
                ENTRY_MAP["number"]: counter,
                ENTRY_MAP["name"]: manager,
                ENTRY_MAP["phone"]: phone_to_send,
                ENTRY_MAP["дата_звонка"]: start_time,
                ENTRY_MAP["тип_звонка"]: call_type,
                ENTRY_MAP["ссылка_клиента"]: customer_card_link
                # Изменено: теперь отправляем ссылку на карточку клиента
            }

            for key in analysis_data:
                if key in ENTRY_MAP and key not in ["name", "тип_звонка", "ссылка_клиента", "call_category",
                                                    "summary"]:  # Обновлен список исключений
                    payload[ENTRY_MAP[key]] = analysis_data[key]

            response = requests.post(FORM_URL, data=payload)
            if response.status_code == 200:
                print(f"[✓] Отправлено в Google Forms: {filename} (Категория: {call_category})")
            else:
                print(
                    f"[✗] Ошибка отправки в Google Forms: {filename} — Status {response.status_code}. Ответ: {response.text}")
        else:
            print(f"⏩ Звонок {filename} (Категория: {call_category}). Пропуск отправки в Google Forms.")

        # --- Логика отправки резюме в Telegram ---
        if call_summary and (
                call_category == "Заказ" or call_category == "Sotrudnichestvo" or call_category == "Сотрудничество"):
            customer_link_formatted = f'<a href="{customer_card_link}">Посмотреть заказ</a>' if customer_card_link else 'Не найдена'  # Изменено для ссылки на карточку клиента

            telegram_message = f"📞 <b>Отчет по звонку №{counter}</b>\n" \
                               f"✨ <b>Категория:</b> <u>{call_category}</u>\n" \
                               f"🗓️ {start_time.split(' ')[0] if start_time else 'Неизвестно'} | {call_type if call_type else 'Неизвестно'}\n\n" \
                               f"👤 Менеджер: <b>{manager}</b>\n" \
                               f"📱 Телефон клиента: <b>{phone_to_send if phone_to_send else 'Неизвестен'}</b>\n" \
                               f"🔗 Ссылка на заказ: {customer_link_formatted}\n\n" \
                               f"📝 <b>Резюме для РОПа:</b>\n{call_summary}"

            send_telegram_message(telegram_message)
        elif not call_summary:
            print(f"ℹ️ Резюме для {filename} не найдено в анализе, в Telegram не отправлено.")
        else:  # Категории, которые не "Заказ" и не "Сотрудничество" (например, "Курьер/Технический" или "Неизвестно")
            print(f"⏩ Звонок {filename} (Категория: {call_category}). Пропуск отправки резюме в Telegram.")

        counter += 1


if __name__ == "__main__":
    today = datetime.today().strftime("%d.%m.%Y")
    folder_name = Path("analyses") / f"транскрибация_{today}"
    send_analyses_to_google_form(folder_name)
