import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pathlib import Path
import re
from typing import List, Dict, Any

# Добавляем корневую директорию проекта в sys.path для импорта retailcrm_integration
import sys

project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Импортируем из розницы
from retailcrm_integration import check_if_phone_has_excluded_order, check_if_phone_has_recent_order

# Load token from .env
load_dotenv()
ACCESS_TOKEN = os.getenv("UIS_API_TOKEN")

# Define Moscow timezone (UTC+3)
MSK = timezone(timedelta(hours=3))


def get_calls_report(date_from, date_to) -> List[Dict[str, Any]]:
    """
    Retrieves call report from UIS server for a specified period.
    Returns a list of call metadata (dictionaries).
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

    print(f"🔍 Получаем список звонков с {date_from} по {date_to}...")

    max_retries = 5
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=(10, 60))
            response.raise_for_status()
            result = response.json()

            calls = result.get("result", {}).get("data", [])
            if not isinstance(calls, list):
                raise ValueError("Неверный формат данных: 'result.data' должен быть списком звонков")

            print(f"✅ Получено {len(calls)} звонков.")
            return calls
        except (requests.exceptions.RequestException, ValueError) as e:
            if attempt < max_retries - 1:
                print(
                    f"⚠️ Ошибка при получении звонков (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {retry_delay} сек...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"❌ Ошибка при получении звонков после {max_retries} попыток: {e}")
                return []
        except Exception as e:
            print(f"❌ Непредвиденная ошибка в get_calls_report: {e}")
            return []


def get_next_call_index(directory):
    """
    Определяет следующий доступный индекс для нового файла звонка.
    """
    existing_files = list(Path(directory).glob("call*.mp3"))
    used_indexes = set()
    for f in existing_files:
        try:
            match = re.match(r'call(\d+)(?:_\d+)?\.mp3', f.name)
            if match:
                number = int(match.group(1))
                used_indexes.add(number)
        except ValueError:
            continue
    return max(used_indexes, default=0) + 1


def _get_call_duration(call: dict) -> int | None:
    """Вспомогательная функция для надежного получения длительности звонка."""
    duration = call.get("total_duration")
    if duration is None:
        duration = call.get("raw", {}).get("total_duration")
    return duration


def download_record(call, index, target_dir) -> Path | None:
    """
    Загружает конкретную запись звонка и сохраняет информацию о нем.
    Возвращает путь к созданному файлу call_info.json.
    """
    talk_id = call.get("communication_id")
    records = call.get("call_records", [])
    total_duration = _get_call_duration(call)

    if not talk_id or not records or total_duration is None or total_duration < 60:
        print(
            f"⏩ Пропускаем звонок {call.get('communication_id', 'N/A')} из-за отсутствия информации или длительности < 60с. Длительность: {total_duration}s")
        return None

    record_hash = records[0]
    record_url = f"https://app.uiscom.ru/system/media/talk/{talk_id}/{record_hash}/"

    # Используем более надежный способ получения номера и направления
    contact_phone = call.get("contact_phone_number") or call.get("raw", {}).get("contact_phone_number", "")
    call_direction = call.get("direction") or call.get("raw", {}).get("direction")

    base_filename = f"call{index}"
    if contact_phone:
        base_filename += f"_{contact_phone}"

    filename = Path(target_dir) / f"{base_filename}.mp3"
    info_filename = Path(target_dir) / f"{base_filename}_call_info.json"

    if filename.exists():
        print(f"⏭ Запись {filename.name} уже существует, пропускаем загрузку.")
    else:
        print(f"⬇ Загружаем {filename.name}...")
        try:
            response = requests.get(record_url, timeout=(10, 30))
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"✅ Сохранено: {filename.name}")
            else:
                print(f"⚠ Ошибка загрузки {record_url}: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка сетевого запроса при загрузке {talk_id}: {e}")
        except Exception as e:
            print(f"❌ Неизвестная ошибка при загрузке {talk_id}: {e}")

    order_link = ""

    try:
        call_info = {
            "start_time": call.get("start_time", ""),
            "raw": call,
            "customer_card_link": order_link,
            "contact_phone_number": contact_phone,
            "record_link": record_url
        }
        with open(info_filename, 'w', encoding='utf-8') as f:
            json.dump(call_info, f, indent=2, ensure_ascii=False)
        print(f"📝 Информация сохранена: {info_filename.name}")
        return info_filename
    except Exception as e:
        print(f"❌ Ошибка сохранения информации о звонке для {talk_id}: {e}")
        return None

# Эта функция была перемещена из тестового блока, чтобы её можно было импортировать
def download_calls(calls_to_download: List[Dict[str, Any]], target_dir: Path) -> List[Path]:
    """
    Загружает только те звонки, которые переданы в списке.
    Возвращает список путей к созданным файлам info.json.
    """
    if not calls_to_download:
        print("ℹ️ Список звонков для загрузки пуст. Пропускаем загрузку.")
        return []

    print(f"🚀 Запускаем загрузку {len(calls_to_download)} звонков.")

    if not ACCESS_TOKEN:
        print("❗ ACCESS_TOKEN не найден в .env. Загрузка невозможна.")
        return []

    downloaded_call_info_paths = []

    try:
        current_idx = get_next_call_index(str(target_dir))
        for call in calls_to_download:
            info_file_path = download_record(call, current_idx, target_dir)
            if info_file_path:
                downloaded_call_info_paths.append(info_file_path)
            current_idx += 1
    except Exception as e:
        print(f"❗ Ошибка выполнения скрипта загрузки звонков: {e}")

    return downloaded_call_info_paths


if __name__ == "__main__":
    # --- БЛОК ТЕСТИРОВАНИЯ С ПОДРОБНЫМ ЛОГИРОВАНИЕМ ---
    # Измените эти значения для тестирования разных дат и времени
    TEST_DATE = "08.09.2025"
    TEST_START_TIME = "12:00:00"
    TEST_END_TIME = "15:00:00"

    try:
        test_start_datetime = datetime.strptime(f"{TEST_DATE} {TEST_START_TIME}", "%d.%m.%Y %H:%M:%S")
        test_end_datetime = datetime.strptime(f"{TEST_DATE} {TEST_END_TIME}", "%d.%m.%Y %H:%M:%S")
    except ValueError:
        print("❌ Неверный формат даты или времени. Используйте формат ДД.ММ.ГГГГ ЧЧ:ММ:СС.")
        exit()

    target_folder_date = test_start_datetime.strftime("%d.%m.%Y")
    target_dir = Path("audio") / f"звонки_{target_folder_date}"
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Тестируем получение списка звонков за {TEST_DATE} с {TEST_START_TIME} по {TEST_END_TIME} ---")
    calls_list = get_calls_report(test_start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                                  test_end_datetime.strftime("%Y-%m-%d %H:%M:%S"))

    if calls_list:
        print("\n--- Запускаем подробную фильтрацию звонков ---")
        filtered_calls = []
        for i, call in enumerate(calls_list):
            call_id = call.get("communication_id", "N/A")
            # Используем более надежный способ получения номера и направления
            phone_number = call.get("contact_phone_number") or call.get("raw", {}).get("contact_phone_number")
            call_direction = call.get("direction") or call.get("raw", {}).get("direction")

            print(f"\n📞 Проверка звонка №{i + 1} (ID: {call_id}) от номера {phone_number}...")

            if not phone_number or not call_direction:
                print(f"❌ Пропускаем: отсутствует номер ({phone_number}) или направление ({call_direction}) звонка.")
                continue

            if call_direction == "in":
                print(f"  ➡️ Направление: ВХОДЯЩИЙ. Проверяем, нет ли исключенных заказов...")
                has_excluded = check_if_phone_has_excluded_order(phone_number)
                if not has_excluded:
                    print(f"  ✅ Звонок прошел фильтр: нет исключенных заказов. Добавляем в список для обработки.")
                    filtered_calls.append(call)
                else:
                    print(f"  ❌ Звонок НЕ прошел фильтр: найден исключенный заказ. Пропускаем.")

            elif call_direction == "out":
                print(f"  ➡️ Направление: ИСХОДЯЩИЙ. Проверяем, есть ли недавний заказ...")
                has_recent = check_if_phone_has_recent_order(phone_number)
                if has_recent:
                    print(f"  ✅ Звонок прошел фильтр: есть недавний заказ. Добавляем в список для обработки.")
                    filtered_calls.append(call)
                else:
                    print(f"  ❌ Звонок НЕ прошел фильтр: нет недавнего заказа. Пропускаем.")

            else:
                print(f"  ⚠️ Неизвестное направление звонка: {call_direction}. Пропускаем.")

        print(f"\n➡️ Итого к обработке: {len(filtered_calls)} звонков из {len(calls_list)}.")

        if filtered_calls:
            print("\n--- Запускаем загрузку отфильтрованных звонков ---")
            downloaded_paths = download_calls(filtered_calls, target_dir)
            print(f"✅ Загрузка завершена. Загружено файлов: {len(downloaded_paths)}")
        else:
            print("Нет звонков, соответствующих критериям фильтрации. Загрузка не требуется.")
    else:
        print("Нет звонков для тестирования в указанном периоде.")

    print("\nТестирование завершено.")


# import requests
# import os
# import json
# import time  # Import time for delays
# from datetime import datetime, timedelta, timezone
# from dotenv import load_dotenv
# from retailcrm_integration import get_order_link_by_phone  # Import function for RetailCRM
# from pathlib import Path
# import re # Import re for get_next_call_index
#
# # Load token from .env
# load_dotenv()
# ACCESS_TOKEN = os.getenv("UIS_API_TOKEN")
#
# # Define Moscow timezone (UTC+3)
# MSK = timezone(timedelta(hours=3))
#
#
# def get_calls_report(date_from, date_to):
#     """
#     Retrieves call report from UIS server for a specified period.
#     Includes retry logic for increased resilience to network errors.
#     """
#     url = 'https://dataapi.uiscom.ru/v2.0'
#     payload = {
#         "id": "id777",
#         "jsonrpc": "2.0",
#         "method": "get.calls_report",
#         "params": {
#             "access_token": ACCESS_TOKEN,
#             "date_from": date_from,
#             "date_till": date_to
#         }
#     }
#
#     print(f"🔍 Getting calls from {date_from} to {date_to}...")
#
#     max_retries = 5  # Maximum number of attempts
#     retry_delay = 1  # Initial delay in seconds (will double)
#
#     for attempt in range(max_retries):
#         try:
#             # Timeout set: 10 sec for connection, 60 sec for read
#             response = requests.post(url, json=payload, timeout=(10, 60))
#             response.raise_for_status()  # Raises an exception for HTTP errors (4xx or 5xx)
#             result = response.json()
#
#             calls = result.get("result", {}).get("data", [])
#             if not isinstance(calls, list):
#                 raise ValueError("Invalid data format: 'result.data' must be a list of calls")
#
#             print(f"✅ Calls received: {len(calls)}")
#             return calls
#         except (requests.exceptions.RequestException, ValueError) as e:
#             # Catch network errors, timeouts, and data format errors
#             if attempt < max_retries - 1:
#                 print(
#                     f"⚠️ Error getting calls (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay} sec...")
#                 time.sleep(retry_delay)
#                 retry_delay *= 2  # Exponential backoff
#             else:
#                 print(f"❌ Error getting calls after {max_retries} attempts: {e}")
#                 return []  # Return empty list after failed attempts
#         except Exception as e:
#             # Catch any other unexpected errors
#             print(f"❌ Unexpected error in get_calls_report: {e}")
#             return []
#
#
# def get_next_call_index(directory):
#     """
#     Determines the next available index for a new callN.mp3 file,
#     to avoid overwriting and continue numbering.
#     Searches for files matching the pattern 'call{index}_{phone_number}.mp3'.
#     """
#     existing_files = list(Path(directory).glob("call*.mp3"))
#     used_indexes = set()
#     for f in existing_files:
#         try:
#             # Extract number from filename (e.g., "call123_79001234567.mp3" -> 123)
#             # Regular expression modified to correctly account for phone number in filename
#             match = re.match(r'call(\d+)(?:_\d+)?\.mp3', f.name)
#             if match:
#                 number = int(match.group(1))
#                 used_indexes.add(number)
#         except ValueError:
#             # Ignore files whose names do not match the pattern
#             continue
#     # Return max used index + 1, or 1 if no files exist
#     return max(used_indexes, default=0) + 1
#
# def _get_call_duration(call: dict) -> int | None:
#     """Helper function to robustly get call duration."""
#     duration = call.get("total_duration") # Try to get directly
#     if duration is None:
#         duration = call.get("raw", {}).get("total_duration") # Fallback to 'raw'
#     return duration
#
#
# def download_record(call, index, target_dir) -> Path | None:
#     """
#     Downloads a specific call recording, saves related information,
#     and searches for an order link in RetailCRM.
#     The filename will be in the format call{index}_{phone_number}.mp3.
#     Returns the path to the created call_info.json file if created, otherwise None.
#     """
#     talk_id = call.get("communication_id")
#     records = call.get("call_records", [])
#     total_duration = _get_call_duration(call) # Use the helper function
#
#     # Skip if no talk ID, no records, or duration is too short
#     if not talk_id or not records or total_duration is None or total_duration < 20:
#         print(f"Warning: Skipping call {call.get('communication_id', 'N/A')} due to missing info or duration < 20s. Duration: {total_duration}s")
#         return None  # Return None, as info file will not be created
#
#     record_hash = records[0]  # Take the hash of the first call record
#     # NEW: Form the full link to the call recording
#     record_url = f"https://app.uiscom.ru/system/media/talk/{talk_id}/{record_hash}/"
#
#     # Phone number can be at the top level or inside "raw"
#     contact_phone = call.get("contact_phone_number") or call.get("raw", {}).get("contact_phone_number", "")
#
#     # Include phone number in filename for consistent identification
#     base_filename = f"call{index}"
#     if contact_phone:
#         base_filename += f"_{contact_phone}"
#
#     filename = Path(target_dir) / f"{base_filename}.mp3"
#     info_filename = Path(target_dir) / f"{base_filename}_call_info.json"
#
#
#     if filename.exists():
#         print(f"⏭ Recording {filename.name} already exists, skipping.")
#     else:
#         print(f"⬇ Downloading {filename.name}...")
#         try:
#             # Timeout set: 10 sec for connection, 30 sec for read
#             response = requests.get(record_url, timeout=(10, 30)) # Use record_url
#             if response.status_code == 200:
#                 with open(filename, 'wb') as f:
#                     f.write(response.content)
#                 print(f"✅ Saved: {filename.name}")
#             else:
#                 print(f"⚠ Download error {record_url}: HTTP {response.status_code}")
#         except requests.exceptions.RequestException as e:
#             print(f"❌ Network request error while downloading {talk_id}: {e}")
#         except Exception as e:
#             print(f"❌ Unknown error while downloading {talk_id}: {e}")
#
#     order_link = ""
#     if contact_phone:
#         order_link = get_order_link_by_phone(contact_phone)
#
#     try:
#         call_info = {
#             "start_time": call.get("start_time", ""),
#             "raw": call,
#             "customer_card_link": order_link,
#             "contact_phone_number": contact_phone,
#             "record_link": record_url # NEW: Add call recording link
#         }
#         with open(info_filename, 'w', encoding='utf-8') as f:
#             json.dump(call_info, f, indent=2, ensure_ascii=False)
#         print(f"📝 Information saved: {info_filename.name}")
#         return info_filename  # Return path to the created file
#     except Exception as e:
#         print(f"❌ Error saving call_info for {talk_id}: {e}")
#         return None  # Return None in case of save error
#
#
# def download_calls(start_time: datetime, end_time: datetime) -> list[Path]:
#     """
#     Main function for downloading calls within a specified period.
#     Returns a list of paths to created call_info.json files.
#     """
#     print("🚀 Starting call download")
#
#     if not ACCESS_TOKEN:
#         print("❗ ACCESS_TOKEN not found in .env. Make sure .env file exists and contains ACCESS_TOKEN.")
#         return []
#
#     date_from_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
#     date_to_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
#
#     folder_date = end_time.strftime("%d.%m.%Y")
#     target_dir = Path("audio") / f"звонки_{folder_date}"
#     target_dir.mkdir(parents=True, exist_ok=True)
#     print(f"Checking or creating call folder: {target_dir}")
#
#     downloaded_call_info_paths = []
#
#     try:
#         calls = get_calls_report(date_from_str, date_to_str)
#         if not calls:
#             print("ℹ️ No calls for the specified period.")
#             return []
#
#         current_idx = get_next_call_index(str(target_dir))
#         for call in calls:
#             # Filter calls by duration (longer than 20 seconds)
#             total_duration = _get_call_duration(call) # Use the helper function
#             if total_duration is None or total_duration < 20:
#                 print(f"⏩ Skipping call {call.get('communication_id', 'N/A')} due to short duration: {total_duration}s")
#                 continue # Skip to the next call
#
#             # Only add path if download_record successfully created the file
#             info_file_path = download_record(call, current_idx, target_dir)
#             if info_file_path:
#                 downloaded_call_info_paths.append(info_file_path)
#             current_idx += 1
#
#     except Exception as e:
#         print(f"❗ Error executing call download script: {e}")
#
#     return downloaded_call_info_paths
#
#
# if __name__ == "__main__":
#     # Example usage for testing the module separately
#     today = datetime.now(MSK)
#     test_start_time = today.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
#     test_end_time = today.replace(hour=23, minute=59, second=59, microsecond=999999) - timedelta(days=1)
#
#     print(
#         f"\n--- Testing download_calls for period: {test_start_time.strftime('%Y-%m-%d %H:%M:%S')} - {test_end_time.strftime('%Y-%m-%d %H:%M:%S')} ---")
#     download_calls(test_start_time, test_end_time)
#     print("\nCall download completed.")