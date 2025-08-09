import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
import re
# Убедитесь, что telegram_bot_integration.py находится в той же директории или в PYTHONPATH
try:
    from telegram_bot_integration import send_telegram_message
except ImportError:
    print("ВНИМАНИЕ: Модуль telegram_bot_integration не найден. Убедитесь, что он существует и доступен.")
    def send_telegram_message(message: str):
        print(f"  ⚠️ Заглушка: send_telegram_message не реализована. Сообщение: {message}")

# Импортируем get_manager_name_from_crm из retailcrm_integration
try:
    from retailcrm_integration import get_manager_name_from_crm
except ImportError:
    print("ВНИМАНИЕ: Модуль retailcrm_integration не найден или get_manager_name_from_crm не определена. Убедитесь, что он существует и доступен.")
    def get_manager_name_from_crm(phone_number: str) -> str:
        print("  ⚠️ Заглушка: retailcrm_integration.get_manager_name_from_crm не реализована. Возвращаем 'Неизвестно'.")
        return "Неизвестно"


# URL вашей Google Forms
FORM_URL = "https://docs.google.com/forms/u/0/d/e/1FAIpQLSeI-BvmkSZgzGXeQB83KQLR0O-5_ALgdhWg9LoMV7DskLqBLQ/formResponse"

# Соответствие полей анализа и названий полей в Google Forms
ENTRY_MAP = {
    "number": "entry.1684791713", # Порядковый номер звонка
    "name": "entry.730205749", # Имя менеджера
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
    "предоплата": "entry.257021647",
    "транскрибация": "entry.2082353450", # НОВОЕ ПОЛЕ: Транскрибация
    "ссылка_на_звонок": "entry.1098563992" # НОВОЕ ПОЛЕ: Ссылка на звонок
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
    Например, для 'call12_79163850107_analysis.json' вернет 12.
    """
    match = re.match(r'call(\d+)_.*_analysis\.json', filename)
    if match:
        return int(match.group(1))
    return 0


def format_duration(seconds: int) -> str:
    """
    Форматирует длительность в секундах в строку "Xм Yс".
    """
    if seconds is None:
        return "Неизвестно"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}м {remaining_seconds}с"


def send_analyses_to_google_form(folder_path: Path, target_folder_date_str: str):
    """
    Отправляет данные анализа звонков в Google Forms и краткое резюме в Telegram,
    учитывая категорию звонка.

    Args:
        folder_path (Path): Путь к папке с JSON-файлами анализа.
        target_folder_date_str (str): Строка с датой папки, которую обрабатываем (например, "25.06.2025").
    """
    # Используем переданную дату для формирования пути к папкам audio и transcripts
    audio_calls_folder = Path("audio") / f"звонки_{target_folder_date_str}"
    transcripts_folder = Path("transcripts") / f"транскрибация_{target_folder_date_str}"


    analysis_files = []
    for filename in os.listdir(folder_path):
        if filename.endswith("_analysis.json"):
            analysis_files.append(filename)

    analysis_files.sort(key=get_call_number_from_filename)

    for filename in analysis_files:
        base_name = filename.replace("_analysis.json", "")
        analysis_path = folder_path / filename
        info_path = audio_calls_folder / f"{base_name}_call_info.json"
        # Путь к файлу транскрипции
        transcript_file_path = transcripts_folder / f"{base_name}.txt"


        call_summary = ""
        analysis_data = {}
        call_category = "Неизвестно"
        call_number_from_file = get_call_number_from_filename(filename)

        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                analysis_data = json.load(f)
                call_summary = analysis_data.get("summary", "")
                call_category = analysis_data.get("call_category", "Неизвестно")
        except FileNotFoundError:
            print(f"Предупреждение: Файл анализа не найден для {base_name}: {analysis_path}. Пропуск.")
            continue
        except json.JSONDecodeError as e:
            print(f"Ошибка декодирования JSON для {analysis_path}: {e}. Пропуск.")
            continue
        except Exception as e:
            print(f"Ошибка при чтении или обработке {analysis_path}: {e}. Пропуск.")
            continue

        start_time = ""
        call_type_with_duration = "Неизвестно"
        order_link = ""
        record_link = "" # НОВОЕ: Инициализация ссылки на запись звонка
        contact_phone_number = ""
        transcript_content = "" # НОВОЕ: Инициализация содержимого транскрипции

        if info_path.exists():
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    call_info = json.load(f)

                start_time = call_info.get("start_time", "")
                direction = call_info.get("raw", {}).get("direction", "")
                total_duration_seconds = call_info.get("raw", {}).get("total_duration")
                record_link = call_info.get("record_link", "") # НОВОЕ: Извлекаем record_link

                duration_formatted = format_duration(total_duration_seconds)

                if direction == "in":
                    call_type_with_duration = f"Входящие ({duration_formatted})"
                elif direction == "out":
                    call_type_with_duration = f"Исходящие ({duration_formatted})"
                else:
                    call_type_with_duration = f"Неизвестно ({duration_formatted})"

                order_link = call_info.get("customer_card_link", "")
                contact_phone_number = call_info.get("contact_phone_number", "")
                if not contact_phone_number:
                    contact_phone_number = call_info.get("raw", {}).get("contact_phone_number", "")

            except json.JSONDecodeError as e:
                print(f"Ошибка декодирования JSON для {info_path}: {e}")
            except Exception as e:
                print(f"Ошибка при чтении или обработке {info_path}: {e}")
        else:
            print(f"Предупреждение: Файл информации о звонке не найден для {base_name}: {info_path}")

        # НОВОЕ: Чтение содержимого транскрипции
        if transcript_file_path.exists():
            try:
                with open(transcript_file_path, "r", encoding="utf-8") as f:
                    transcript_content = f.read()
            except Exception as e:
                print(f"Ошибка при чтении файла транскрипции {transcript_file_path}: {e}")
        else:
            print(f"Предупреждение: Файл транскрипции не найден для {base_name}: {transcript_file_path}")


        # --- Логика получения имени менеджера из CRM, если оно "Неизвестно" ---
        manager = analysis_data.get("manager_name", "Неизвестно")
        phone_to_send = contact_phone_number

        phone_number_match = re.search(r'call\d+_(\d+)_analysis\.json', analysis_path.name)
        phone_number_from_filename = phone_number_match.group(1) if phone_number_match else None

        if manager == "Неизвестно" and phone_number_from_filename:
            print(f"  🔍 Менеджер не определен для {analysis_path.name}. Попытка получить из RetailCRM по номеру {phone_number_from_filename}...")
            crm_manager_name = get_manager_name_from_crm(phone_number_from_filename)
            if crm_manager_name:
                manager = crm_manager_name
                print(f"  ✅ Имя менеджера обновлено на: {crm_manager_name} (из RetailCRM)")
            else:
                print(f"  ❌ Не удалось получить имя менеджера из RetailCRM для {analysis_path.name}")


        # --- Логика отправки в Google Forms ---
        if call_category == "Заказ":
            payload = {
                ENTRY_MAP["number"]: call_number_from_file,
                ENTRY_MAP["name"]: manager,
                ENTRY_MAP["phone"]: phone_to_send,
                ENTRY_MAP["дата_звонка"]: start_time,
                ENTRY_MAP["тип_звонка"]: call_type_with_duration,
                ENTRY_MAP["ссылка_заказ"]: order_link,
                ENTRY_MAP["транскрибация"]: transcript_content, # НОВОЕ: Добавляем транскрибацию
                ENTRY_MAP["ссылка_на_звонок"]: record_link # НОВОЕ: Добавляем ссылку на звонок
            }

            for key in analysis_data:
                if key in ENTRY_MAP and key not in ["name", "тип_звонка", "ссылка_заказ", "call_category", "summary", "manager_name", "транскрибация", "ссылка_на_звонок"]:
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
        if call_summary and call_category in ["Заказ", "Сотрудничество"]:
            order_link_formatted = f'<a href="{order_link}">Посмотреть заказ</a>' if order_link else 'Не найдена'
            record_link_formatted = f'<a href="{record_link}">Прослушать звонок</a>' if record_link else 'Не найдена' # НОВОЕ: Ссылка на запись

            telegram_message = f"📞 <b>Отчет по звонку №{call_number_from_file}</b>\n" \
                               f"✨ <b>Категория:</b> <u>{call_category}</u>\n" \
                               f"🗓️ {start_time.split(' ')[0] if start_time else 'Неизвестно'} | {call_type_with_duration}\n\n" \
                               f"👤 Менеджер: <b>{manager}</b>\n" \
                               f"📱 Телефон клиента: <b>{phone_to_send if phone_to_send else 'Неизвестен'}</b>\n" \
                               f"🔗 Ссылка на заказ: {order_link_formatted}\n" \
                               f"🎧 Ссылка на запись: {record_link_formatted}\n\n" \
                               f"📝 <b>Резюме для РОПа:</b>\n{call_summary}"

            send_telegram_message(telegram_message)
        elif not call_summary:
            print(f"ℹ️ Резюме для {filename} не найдено в анализе, в Telegram не отправлено.")
        else:
            print(f"⏩ Звонок {filename} (Категория: {call_category}). Пропуск отправки резюме в Telegram.")


if __name__ == "__main__":
    # Для тестирования модуля отдельно, используйте текущую дату
    today_str = datetime.today().strftime("%d.%m.%Y")
    folder_name = Path("analyses") / f"транскрибация_{today_str}"
    send_analyses_to_google_form(folder_name, today_str)