import os
import sys
import shutil
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import time

# Добавляем корневую директорию проекта в sys.path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Импортируем необходимые модули
from uis_call_downloader import get_calls_report, download_record, download_calls
from transcriber import transcribe_all
from analyzer import analyze_transcripts
from google_sheets import send_analyses_to_google_form
# ИСПРАВЛЕНИЕ: check_if_phone_has_recent_order больше не используется для фильтрации в main.py
from retailcrm_integration import check_if_last_order_is_analyzable, check_if_phone_has_recent_order, \
    get_order_link_by_phone

# Define Moscow timezone (UTC+3)
MSK = timezone(timedelta(hours=3))


def clean_old_folders(base_dir: Path, days_to_keep: int):
    """
    Удаляет старые папки в указанной базовой директории.
    """
    print(f"\n🧹 Запускаем очистку старых папок в {base_dir} (сохраняем за последние {days_to_keep} дней)...")
    current_time_msk = datetime.now(MSK)
    cutoff_date = (current_time_msk - timedelta(days=days_to_keep)).date()
    if not base_dir.exists():
        print(f"Директория {base_dir} не существует. Пропускаем очистку.")
        return
    for folder in base_dir.iterdir():
        if folder.is_dir():
            try:
                date_str_part = folder.name.split('_')[-1]
                folder_date = datetime.strptime(date_str_part, "%d.%m.%Y").date()
                if folder_date < cutoff_date:
                    print(
                        f"🗑️ Удаляем старую папку: {folder} (дата {folder_date.strftime('%d.%m.%Y')} старше {cutoff_date.strftime('%d.%m.%Y')})")
                    shutil.rmtree(folder)
                else:
                    print(f"✅ Сохраняем папку: {folder} (дата {folder_date.strftime('%d.%m.%Y')})")
            except ValueError:
                print(f"⚠️ Пропускаем папку {folder.name}: не удалось извлечь дату из имени или неверный формат.")
            except Exception as e:
                print(f"❌ Ошибка при удалении папки {folder.name}: {e}")
    print(f"Очистка в {base_dir} завершена.")


def send_all_analyses_to_integrations(analyses_folder_path: Path, target_folder_date_str: str):
    """
    Отправляет сгенерированные JSON-файлы анализов в Google Forms.
    """
    print("\n--- Отправка анализов в Google Forms (и Telegram, если настроено) ---")
    if not analyses_folder_path.exists():
        print(f"Папка с анализами не найдена: {analyses_folder_path}. Пропускаем отправку.")
        return
    print(f"\n  ➡️ Запускаем отправку всех целевых анализов в Google Forms из {analyses_folder_path}.")
    send_analyses_to_google_form(analyses_folder_path, target_folder_date_str)


def run_processing_pipeline():
    """
    Определяет текущий временной диапазон для обработки звонков
    на основе текущего времени по МСК и запускает пайплайн.
    """
    current_time_msk = datetime.now(MSK)
    current_hour_msk = current_time_msk.hour
    current_date_msk = current_time_msk.date()

    print(f"Текущее время по МСК: {current_time_msk.strftime('%Y-%m-%d %H:%M:%S')}")

    # Очищаем старые папки
    clean_old_folders(Path("audio"), 1)
    clean_old_folders(Path("transcripts"), 1)
    clean_old_folders(Path("analyses"), 1)

    start_time_period = None
    end_time_period = None
    target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")

    # Определение периодов обработки по времени суток
    if current_hour_msk == 12:
        yesterday_date_msk = current_date_msk - timedelta(days=1)
        print("Определен период обработки: утренние звонки (с вечера вчера до полудня сегодня)")
        start_time_period = datetime.combine(yesterday_date_msk, datetime.min.time().replace(hour=19), tzinfo=MSK)
        end_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=11, minute=59, second=59),
                                           tzinfo=MSK)
        target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")

    elif current_hour_msk == 15:
        print("Определен период обработки: дневные звонки (с полудня сегодня до 15:00 сегодня)")
        start_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=12), tzinfo=MSK)
        end_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=14, minute=59, second=59),
                                           tzinfo=MSK)
        target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")

    elif current_hour_msk == 19:
        print("Определен период обработки: вечерние звонки (с 15:00 сегодня до 19:00 сегодня)")
        start_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=15), tzinfo=MSK)
        end_time_period = datetime.combine(current_time_msk, datetime.min.time().replace(hour=18, minute=59, second=59),
                                           tzinfo=MSK)
        target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
    else:
        print(
            "Текущее время не соответствует запланированным периодам обработки (12:00, 15:00, 19:00 МСК). Пропускаю выполнение.")
        return

    if start_time_period and end_time_period:
        print(
            f"Обработка звонков за период: {start_time_period.strftime('%Y-%m-%d %H:%M:%S')} - {end_time_period.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Целевая дата папок для обработки: {target_folder_date_str}")

        # --- НОВАЯ ЛОГИКА ---
        # 1. Получаем список всех звонков с метаданными
        print("\n--- Получение списка звонков с метаданными ---")
        calls = get_calls_report(start_time_period.strftime("%Y-%m-%d %H:%M:%S"),
                                 end_time_period.strftime("%Y-%m-%d %H:%M:%S"))

        if not calls:
            print("ℹ️ Нет звонков для обработки в указанном периоде.")
            print("\n✅ Пайплайн обработки звонков завершен.")
            return

        # 2. Фильтруем звонки по новым бизнес-правилам и готовим список к загрузке
        print("\n--- Фильтрация звонков по правилам бизнеса ---")
        calls_to_download_and_process = []
        for call in calls:
            phone_number = call.get("contact_phone_number") or call.get("raw", {}).get("contact_phone_number")
            call_direction = call.get("direction") or call.get("raw", {}).get("direction")

            # Если нет номера или направления - пропускаем звонок.
            if not phone_number or not call_direction:
                print(f"⚠️ Пропускаем звонок из-за отсутствия номера или направления: {call.get('communication_id')}")
                continue

            # Единственное правило: проверка статуса последнего заказа (для IN и OUT звонков)
            if check_if_last_order_is_analyzable(phone_number):
                if call_direction == "in":
                    print(f"✅ Входящий звонок с номера {phone_number} прошел фильтр (статус последнего заказа разрешен к анализу или заказов нет).")
                    calls_to_download_and_process.append(call)
                elif call_direction == "out":
                    # ИСПРАВЛЕНО: Исходящие звонки теперь фильтруются только по статусу заказа
                    print(f"✅ Исходящий звонок на номер {phone_number} прошел фильтр (статус последнего заказа разрешен к анализу или заказов нет).")
                    calls_to_download_and_process.append(call)
            else:
                # В новой логике False означает, что последний заказ в НЕанализируемом статусе (Закупка, Комплектация, Доставка и т.п.)
                print(f"❌ Звонок ({call_direction}) с/на номер {phone_number} НЕ прошел фильтр (последний заказ НЕ разрешен к анализу).")


        print(f"➡️ Итого к загрузке и обработке: {len(calls_to_download_and_process)} звонков.")

        if not calls_to_download_and_process:
            print("Нет звонков, соответствующих критериям фильтрации.")
            print("\n✅ Пайплайн обработки звонков завершен.")
            return

        # 3. Загружаем и обрабатываем только отфильтрованные звонки
        audio_dir = Path("audio") / f"звонки_{target_folder_date_str}"
        audio_dir.mkdir(parents=True, exist_ok=True)
        print("\n--- Загрузка отфильтрованных звонков ---")
        # Здесь мы используем существующую функцию download_calls, передавая ей только нужные звонки.
        downloaded_call_info_paths = download_calls(calls_to_download_and_process, audio_dir)
        print(f"Статус папки аудио: {audio_dir.exists()} (содержит {len(list(audio_dir.glob('*.mp3')))} mp3 файлов)")

        # 4. Транскрибация и анализ
        if downloaded_call_info_paths:
            print("\n--- Транскрибация звонков ---")
            transcribe_all(target_folder_date_str, assign_roles=True)
            transcripts_dir = Path("transcripts") / f"транскрибация_{target_folder_date_str}"
            print(
                f"Статус папки транскриптов: {transcripts_dir.exists()} (содержит {len(list(transcripts_dir.glob('*.txt')))} txt файлов)")

            print("\n--- Анализ транскриптов ---")
            analyze_transcripts(target_folder_date_str)
            analyses_dir = Path("analyses") / f"транскрибация_{target_folder_date_str}"
            print(
                f"Статус папки анализов: {analyses_dir.exists()} (содержит {len(list(analyses_dir.glob('*_analysis.json')))} json файлов)")

            # 5. Отправка анализов
            send_all_analyses_to_integrations(analyses_dir, target_folder_date_str)

    print("\n✅ Пайплайн обработки звонков завершен.")


if __name__ == "__main__":
    print("🚀 Запуск пайплайна...")
    run_processing_pipeline()
    print("\n✅ Скрипт успешно завершил работу.")
