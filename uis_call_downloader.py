import requests
import datetime
import os
import socket
from dotenv import load_dotenv


# ==== Конфигурация ====
load_dotenv()
token_raw = os.getenv("UIS_API_TOKEN")
UIS_API_TOKEN = f"Bearer {token_raw}"
DOWNLOAD_DIR = 'downloads'

# Даты: вчера → сегодня
START_DATE = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
END_DATE = datetime.date.today().isoformat()

HEADERS = {
    'Authorization': UIS_API_TOKEN,
    'Content-Type': 'application/json'
}


def is_connected():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def get_call_sessions(start_date, end_date):
    url = 'https://dataapi.uiscom.ru/v2/reports/calls'
    payload = {
        "date_from": start_date,
        "date_to": end_date,
        "limit": 100,
        "offset": 0
    }

    print(f"🔍 Получаем список звонков с {start_date} по {end_date}...")
    response = requests.post(url, json=payload, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    sessions = [call['call_session_id'] for call in data.get('data', [])]
    print(f"✅ Найдено звонков: {len(sessions)}")
    return sessions


def get_media_links(session_ids):
    url = 'https://dataapi.uiscom.ru/media_files'
    payload = {"call_session_ids": session_ids}

    print("🔗 Получаем ссылки на записи...")
    response = requests.post(url, json=payload, headers=HEADERS, verify=True)
    response.raise_for_status()
    data = response.json()
    media_dict = {
        entry['call_session_id']: entry['media_url']
        for entry in data.get('data', [])
        if entry.get('media_url')
    }
    print(f"🎧 Ссылок на записи: {len(media_dict)}")
    return media_dict


def download_files(media_dict):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for session_id, url in media_dict.items():
        try:
            print(f"⬇ Скачиваем звонок {session_id}...")
            response = requests.get(url)
            if response.status_code == 200:
                filename = os.path.join(DOWNLOAD_DIR, f'{session_id}.mp3')
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"✅ Сохранено: {filename}")
            else:
                print(f"⚠ Ошибка скачивания {session_id}: HTTP {response.status_code}")
        except Exception as e:
            print(f"❌ Ошибка при скачивании {session_id}: {e}")


# ==== Главный запуск ====
if __name__ == '__main__':
    print("🚀 Старт скрипта")
    if not is_connected():
        print("❌ Нет подключения к интернету. Завершение.")
        exit()

    try:
        sessions = get_call_sessions(START_DATE, END_DATE)
        if sessions:
            media_links = get_media_links(sessions)
            if media_links:
                download_files(media_links)
            else:
                print("ℹ Нет доступных ссылок на звонки.")
        else:
            print("ℹ Нет звонков за указанный период.")
    except Exception as e:
        print(f"❗ Ошибка выполнения скрипта: {e}")
