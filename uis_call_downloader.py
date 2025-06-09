import requests
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Загрузка токена из .env
load_dotenv()
ACCESS_TOKEN = os.getenv("UIS_API_TOKEN")


def get_calls_report(date_from, date_to):
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
    response.raise_for_status()
    result = response.json()

    calls = result.get("result", {}).get("data", [])
    if not isinstance(calls, list):
        raise ValueError("Неверный формат данных: 'result.data' должен быть списком вызовов")

    print(f"✅ Получено звонков: {len(calls)}")
    return calls


def download_record(call, index, target_dir):
    talk_id = call.get("communication_id")
    records = call.get("call_records", [])
    if not talk_id or not records:
        return

    record_hash = records[0]  # берём первый элемент
    url = f"https://app.uiscom.ru/system/media/talk/{talk_id}/{record_hash}/"
    filename = os.path.join(target_dir, f"call{index}.mp3")

    if os.path.exists(filename):
        print(f"⏭ Запись {filename} уже существует, пропускаем.")
        return

    print(f"⬇ Скачиваем {filename}...")
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"✅ Сохранено: {filename}")
        else:
            print(f"⚠ Ошибка скачивания: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка при скачивании {talk_id}: {e}")


def download_calls():
    print("🚀 Старт скрипта")

    if not ACCESS_TOKEN:
        print("❗ ACCESS_TOKEN не найден в .env")
        return

    # Динамически рассчитываем дату "вчера"
    date_to = datetime.now().replace(hour=23, minute=59, second=59)
    date_from = (date_to - timedelta(days=1)).replace(hour=0, minute=0, second=0)

    date_from_str = date_from.strftime("%Y-%m-%d %H:%M:%S")
    date_to_str = date_to.strftime("%Y-%m-%d %H:%M:%S")
    folder_date = date_from.strftime("%d.%m.%Y")
    target_dir = os.path.join("audio", f"звонки_{folder_date}")
    os.makedirs(target_dir, exist_ok=True)

    try:
        calls = get_calls_report(date_from_str, date_to_str)
        if calls:
            print("📦 Пример содержимого вызова:", json.dumps(calls[0], indent=2, ensure_ascii=False))
        else:
            print("ℹ️ Нет звонков за указанный период.")

        for idx, call in enumerate(calls, start=1):
            download_record(call, idx, target_dir)
    except Exception as e:
        print(f"❗ Ошибка выполнения скрипта: {e}")


if __name__ == "__main__":
    download_calls()
