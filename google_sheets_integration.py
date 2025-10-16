import pandas as pd
from typing import Set
from pathlib import Path
import requests
import os

# Предполагаем, что столбец называется именно так
ORDER_LINK_COLUMN = "Ссылка на заказ"

# ИЗМЕНЕНИЕ: Добавлен &gid={gid} в URL для скачивания конкретной вкладки
DOWNLOAD_BASE_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx&gid={gid}"


def download_google_sheet_as_xlsx(sheet_id: str, gid: str, file_path: Path) -> bool:
    """
    Скачивает Google Sheet по ID и GID в формате XLSX и сохраняет по указанному пути.

    Args:
        sheet_id (str): ID Google Sheet.
        gid (str): ID вкладки (sheet). <--- НОВЫЙ ПАРАМЕТР
        file_path (Path): Путь для сохранения XLSX файла.

    Returns:
        bool: True, если скачивание успешно, False в противном случае.
    """
    # ИЗМЕНЕНИЕ: Теперь URL формируется с использованием gid
    url = DOWNLOAD_BASE_URL.format(sheet_id=sheet_id, gid=gid)
    print(f"⬇️ Пытаемся скачать Google Sheet по ID: {sheet_id}, GID: {gid}...")

    # ВАЖНО: предполагается, что таблица имеет настройки доступа "Anyone with the link"
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()  # Проверка на HTTP ошибки (4xx или 5xx)

        # Проверка, что скачался не HTML (страница ошибки, требующая авторизации)
        content_type = response.headers.get('Content-Type', '')
        if "text/html" in content_type:
            print(f"❌ Ошибка скачивания: Получен HTML-ответ (Content-Type: {content_type}). Возможно, требуется авторизация или неверный ID/URL.")
            return False

        with open(file_path, 'wb') as f:
            f.write(response.content)

        print(f"✅ Файл успешно скачан и сохранен как {file_path.name}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сетевого запроса при скачивании Google Sheets: {e}")
        return False
    except Exception as e:
        print(f"❌ Непредвиденная ошибка при скачивании: {e}")
        return False


def load_analyzed_order_links(file_path: Path) -> Set[str]:
    """
    Загружает XLSX-файл, ищет столбец 'Ссылка на заказ' и возвращает
    множество уникальных ссылок для быстрого поиска.

    Args:
        file_path (Path): Путь к локально скачанному XLSX-файлу.

    Returns:
        Set[str]: Множество уникальных строк-ссылок.
    """
    if not file_path.exists():
        print(f"⚠️ Файл для проверки ссылок не найден: {file_path}")
        return set()

    try:
        # Читаем только нужный столбец
        # (Осталось без изменений, так как pandas считывает первый лист по умолчанию,
        # но при скачивании по GID мы гарантируем, что этот лист - нужный)
        df = pd.read_excel(file_path, engine='openpyxl', usecols=[ORDER_LINK_COLUMN], dtype=str)

        if ORDER_LINK_COLUMN not in df.columns:
            print(f"❌ Ошибка: В файле {file_path.name} не найден столбец '{ORDER_LINK_COLUMN}'.")
            return set()

        # Очищаем от пустых значений и возвращаем множество уникальных ссылок
        links = {str(x).strip() for x in df[ORDER_LINK_COLUMN].dropna().unique() if str(x).strip()}
        print(f"✅ Успешно загружено {len(links)} уникальных ссылок на заказы из таблицы.")
        return links

    except FileNotFoundError:
        print(f"❌ Ошибка: Файл не найден по пути {file_path}")
        return set()
    except Exception as e:
        print(f"❌ Непредвиденная ошибка при чтении XLSX: {e}")
        return set()