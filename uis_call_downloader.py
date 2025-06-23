import requests
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from retailcrm_integration import get_customer_card_link_by_phone  # Исправлено: Импортируем правильное имя функции
from pathlib import Path  # Импортируем Path для работы с путями

# Загрузка токена из .env
load_dotenv()
ACCESS_TOKEN = os.getenv("UIS_API_TOKEN")


def get_calls_report(date_from, date_to):
    """
    Получает отчет о звонках с сервера UIS за указанный период.
    """
    url = 'https://dataapi.uiscom.ru/v2.0'
    payload = {
        "id": "id777",
        "jsonrpc": "2.0",
        "method": "get.calls_report",
        "params": {
            "access_token": ACCESS_TOKEN,
            "date_from": date_from,
            "date_till": date_to
        }
    }

    print(f"🔍 Получаем звонки с {date_from} по {date_to}...")
    response = requests.post(url, json=payload)
    response.raise_for_status()  # Вызывает исключение для HTTP ошибок (4xx или 5xx)
    result = response.json()

    calls = result.get("result", {}).get("data", [])
    if not isinstance(calls, list):
        raise ValueError("Неверный формат данных: 'result.data' должен быть списком вызовов")

    print(f"✅ Получено звонков: {len(calls)}")
    return calls


def get_next_call_index(directory):
    """
    Определяет следующий доступный индекс для нового файла callN.mp3,
    чтобы избежать перезаписи и продолжить нумерацию.
    """
    existing = [f for f in os.listdir(directory) if f.startswith("call") and f.endswith(".mp3")]
    used_indexes = set()
    for f in existing:
        try:
            # Извлекаем число из имени файла (например, "call123.mp3" -> 123)
            number = int(f.replace("call", "").replace(".mp3", ""))
            used_indexes.add(number)
        except ValueError:
            # Игнорируем файлы, имена которых не соответствуют шаблону
            continue
    # Возвращаем максимальный использованный индекс + 1, или 1, если файлов нет
    return max(used_indexes, default=0) + 1


def download_record(call, index, target_dir):
    """
    Скачивает запись конкретного звонка, сохраняет связанную с ним информацию
    и ищет ссылку на карточку клиента в RetailCRM.
    """
    talk_id = call.get("communication_id")
    records = call.get("call_records", [])

    # Пропускаем, если нет ID разговора или записей
    if not talk_id or not records:
        print(f"Предупреждение: Пропуск звонка без communication_id или записей: {call}")
        return

    record_hash = records[0]  # Берём хеш первой записи звонка
    url = f"https://app.uiscom.ru/system/media/talk/{talk_id}/{record_hash}/"

    filename = Path(target_dir) / f"call{index}.mp3"  # Используем Path
    info_filename = Path(target_dir) / f"call{index}_call_info.json"  # Используем Path

    if filename.exists():  # Используем .exists() для Path
        print(f"⏭ Запись {filename.name} уже существует, пропускаем.")  # .name для чистого имени
    else:
        print(f"⬇ Скачиваем {filename.name}...")
        try:
            response = requests.get(url)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"✅ Сохранено: {filename.name}")
            else:
                print(f"⚠ Ошибка скачивания {url}: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка сетевого запроса при скачивании {talk_id}: {e}")
        except Exception as e:
            print(f"❌ Неизвестная ошибка при скачивании {talk_id}: {e}")

    # --- Новая логика для получения ссылки на карточку клиента из RetailCRM ---
    customer_card_link = "" # Переименовано с order_link на customer_card_link
    contact_phone = call.get("contact_phone_number", "")  # Исправлено: "contact_phone_number" находится не в "raw"

    print(
        f"DEBUG: Номер телефона клиента из UIS звонка для поиска карточки клиента: {contact_phone}")  # <-- Добавлено отладочное сообщение
    if contact_phone:
        customer_card_link = get_customer_card_link_by_phone(contact_phone) # Исправлено: вызываем правильную функцию
    else:
        print("DEBUG: Номер телефона клиента отсутствует в данных звонка UIS. Ссылка на карточку клиента не будет искаться.")
    # ------------------------------------------------------------------

    # Сохраняем информацию о звонке, теперь включая ссылку на карточку клиента
    try:
        call_info = {
            "start_time": call.get("start_time", ""),
            "raw": call,  # Сохраняем все сырые данные звонка для полноты
            "customer_card_link": customer_card_link  # Добавляем ссылку на карточку клиента
        }
        with open(info_filename, 'w', encoding='utf-8') as f:
            json.dump(call_info, f, indent=2, ensure_ascii=False)
        print(f"📝 Сохранена информация: {info_filename.name}")  # .name для чистого имени
    except Exception as e:
        print(f"❌ Ошибка при сохранении call_info для {talk_id}: {e}")


def download_calls():
    """
    Основная функция для скачивания всех звонков за вчерашний день.
    """
    print("🚀 Старт скрипта")

    if not ACCESS_TOKEN:
        print("❗ ACCESS_TOKEN не найден в .env. Убедитесь, что файл .env существует и содержит ACCESS_TOKEN.")
        return

    # --- Коррекция временного промежутка для получения ЗВОНКОВ ЗА ВЧЕРАШНИЙ ДЕНЬ ---
    yesterday = datetime.now().astimezone() - timedelta(days=1)

    # Дата начала вчерашнего дня (12:00:00)
    date_from = yesterday.replace(hour=12, minute=0, second=0, microsecond=0)
    # Дата окончания вчерашнего дня (13:59:59 - чтобы охватить до 14:00, но не включая 14:00:00 следующего часа)
    date_to = yesterday.replace(hour=15, minute=20, second=59, microsecond=0)
    # -------------------------------------------------------------------------

    date_from_str = date_from.strftime("%Y-%m-%d %H:%M:%S")
    date_to_str = date_to.strftime("%Y-%m-%d %H:%M:%S")

    # Формируем имя папки на основе даты "from"
    folder_date = date_from.strftime("%d.%m.%Y")
    target_dir = Path("audio") / f"звонки_{folder_date}"  # Используем Path
    target_dir.mkdir(parents=True, exist_ok=True)  # Используем mkdir для Path
    print(f"Проверяем или создаем папку для звонков: {target_dir}")

    try:
        calls = get_calls_report(date_from_str, date_to_str)
        if not calls:
            print("ℹ️ Нет звонков за указанный период.")
            return  # Выходим, если звонков нет

        # Если есть звонки, выводим пример первого для отладки
        print("📦 Пример содержимого первого вызова:", json.dumps(calls[0], indent=2, ensure_ascii=False))

        current_idx = get_next_call_index(str(target_dir))  # get_next_call_index ожидает строку
        for call in calls:
            print(f"\n🔹 Звонок #{current_idx}:")
            # print(json.dumps(call, indent=2, ensure_ascii=False)) # Можно раскомментировать для детальной отладки
            download_record(call, current_idx, target_dir)  # target_dir теперь Path объект
            current_idx += 1  # Увеличиваем индекс для следующего звонка

    except Exception as e:
        print(f"❗ Ошибка выполнения скрипта: {e}")


if __name__ == "__main__":
    download_calls()
