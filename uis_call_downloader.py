import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pathlib import Path
import re
from typing import List, Dict, Any, Optional

# Добавляем корневую директорию проекта в sys.path для импорта retailcrm_integration
import sys

project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Импортируем из розницы
# ИСПРАВЛЕНИЕ: Оставлена только check_if_last_order_is_analyzable, так как check_if_phone_has_recent_order больше не используется для фильтрации.
from retailcrm_integration import check_if_last_order_is_analyzable

# Load token from .env
load_dotenv()
ACCESS_TOKEN = os.getenv("UIS_API_TOKEN")

# Define Moscow timezone (UTC+3)
MSK = timezone(timedelta(hours=3))


def get_calls_report(date_from: str, date_to: str) -> List[Dict[str, Any]]:
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


def get_next_call_index(directory: str) -> int:
    """
    Определяет следующий доступный индекс для нового файла звонка.
    """
    existing_files = list(Path(directory).glob("call*.mp3"))
    used_indexes = set()
    for f in existing_files:
        try:
            # Обновлено регулярное выражение для более точного соответствия callN_phone.mp3
            match = re.match(r'call(\d+)(?:_\d+)?\.mp3', f.name)
            if match:
                number = int(match.group(1))
                used_indexes.add(number)
        except ValueError:
            continue
    return max(used_indexes, default=0) + 1


def _get_call_duration(call: dict) -> Optional[int]:
    """Вспомогательная функция для надежного получения длительности звонка."""
    duration = call.get("total_duration")
    if duration is None:
        duration = call.get("raw", {}).get("total_duration")
    return duration


def download_record(call: Dict[str, Any], index: int, target_dir: Path) -> Optional[Path]:
    """
    Загружает конкретную запись звонка и сохраняет информацию о нем.
    Возвращает путь к созданному файлу call_info.json.
    """
    talk_id = call.get("communication_id")
    records = call.get("call_records", [])
    total_duration = _get_call_duration(call)

    if not talk_id or not records or total_duration is None or total_duration <= 60:
        print(
            f"⏩ Пропускаем звонок {call.get('communication_id', 'N/A')} из-за отсутствия информации или длительности < 60с. Длительность: {total_duration}s")
        return None

    record_hash = records[0]
    record_url = f"https://app.uiscom.ru/system/media/talk/{talk_id}/{record_hash}/"

    # Используем более надежный способ получения номера и направления
    contact_phone = call.get("contact_phone_number") or call.get("raw", {}).get("contact_phone_number", "")
    # call_direction = call.get("direction") or call.get("raw", {}).get("direction") # не используется

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

            # ИСПРАВЛЕНИЕ: Унифицированная фильтрация по статусу последнего заказа для IN и OUT звонков
            if call_direction == "in" or call_direction == "out":
                print(f"  ➡️ Направление: {call_direction.upper()}. Проверяем, разрешен ли последний заказ к анализу...")
                is_analyzable = check_if_last_order_is_analyzable(phone_number)
                if is_analyzable:
                    print(f"  ✅ Звонок прошел фильтр: последний заказ разрешен к анализу (или заказов нет). Добавляем в список для обработки.")
                    filtered_calls.append(call)
                else:
                    # В новой логике False означает, что последний заказ в НЕанализируемом статусе
                    print(f"  ❌ Звонок НЕ прошел фильтр: последний заказ НЕ разрешен к анализу. Пропускаем.")
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
