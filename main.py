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
from uis_call_downloader import get_calls_report, download_calls
from transcriber import transcribe_all
from analyzer import analyze_transcripts
from google_sheets import send_analyses_to_google_form
from retailcrm_integration import check_if_phone_has_excluded_order, check_if_phone_has_recent_order, \
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
        # 1. Получаем список всех звонков с метаданными (без загрузки аудио)
        print("\n--- Получение списка звонков с метаданными ---")
        calls = get_calls_report(start_time_period.strftime("%Y-%m-%d %H:%M:%S"),
                                 end_time_period.strftime("%Y-%m-%d %H:%M:%S"))

        if not calls:
            print("ℹ️ Нет звонков для обработки в указанном периоде.")
            print("\n✅ Пайплайн обработки звонков завершен.")
            return

        # 2. Фильтруем звонки по новым бизнес-правилам
        print("\n--- Фильтрация звонков по правилам бизнеса ---")
        calls_to_process = []
        for call in calls:
            phone_number = call.get("contact_phone_number")
            call_direction = call.get("raw", {}).get("direction")
            if not phone_number or not call_direction:
                print(f"⚠️ Пропускаем звонок из-за отсутствия номера или направления: {call.get('communication_id')}")
                continue

            # Правило 1: Входящие звонки
            if call_direction == "in":
                if not check_if_phone_has_excluded_order(phone_number):
                    print(f"✅ Входящий звонок с номера {phone_number} прошел фильтр (нет исключенных статусов).")
                    calls_to_process.append(call)
                else:
                    print(f"❌ Входящий звонок с номера {phone_number} НЕ прошел фильтр (есть исключенный статус).")

            # Правило 2: Исходящие звонки
            elif call_direction == "out":
                if check_if_phone_has_recent_order(phone_number):
                    print(f"✅ Исходящий звонок на номер {phone_number} прошел фильтр (есть недавний заказ).")
                    calls_to_process.append(call)
                else:
                    print(f"❌ Исходящий звонок на номер {phone_number} НЕ прошел фильтр (нет недавнего заказа).")

        print(f"➡️ Итого к обработке: {len(calls_to_process)} звонков.")
        if not calls_to_process:
            print("Нет звонков, соответствующих критериям фильтрации.")
            print("\n✅ Пайплайн обработки звонков завершен.")
            return

        # 3. Загружаем и обрабатываем только отфильтрованные звонки
        audio_dir = Path("audio") / f"звонки_{target_folder_date_str}"
        audio_dir.mkdir(parents=True, exist_ok=True)
        print("\n--- Загрузка отфильтрованных звонков ---")
        downloaded_call_info_paths = download_calls(calls_to_process, audio_dir)
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


# import os
# import sys
# import shutil
# import json
# from datetime import datetime, timedelta, timezone
# from pathlib import Path
# import re
# import time
#
# # Добавляем корневую директорию проекта в sys.path, если она еще не там.
# project_root = Path(__file__).resolve().parent
# if str(project_root) not in sys.path:
#     sys.path.append(str(project_root))
#
# # Импортируем необходимые модули
# # Предполагается, что эти файлы существуют и содержат необходимые функции
# from uis_call_downloader import download_calls, MSK
# from transcriber import transcribe_all
# from analyzer import analyze_transcripts
# from google_sheets import send_analyses_to_google_form
#
# def clean_old_folders(base_dir: Path, days_to_keep: int):
#     """
#     Удаляет папки в указанной базовой директории, если их дата старше,
#     чем days_to_keep дней (считая по дате в названии папки).
#     """
#     print(f"\n🧹 Запускаем очистку старых папок в {base_dir} (сохраняем за последние {days_to_keep} дней)...")
#
#     current_time_msk = datetime.now(MSK)
#     cutoff_date = (current_time_msk - timedelta(days=days_to_keep)).date()
#
#     if not base_dir.exists():
#         print(f"Директория {base_dir} не существует. Пропускаем очистку.")
#         return
#
#     for folder in base_dir.iterdir():
#         if folder.is_dir():
#             try:
#                 # Извлекаем дату из имени папки, например "звонки_07.08.2025"
#                 date_str_part = folder.name.split('_')[-1]
#                 folder_date = datetime.strptime(date_str_part, "%d.%m.%Y").date()
#
#                 if folder_date < cutoff_date:
#                     print(
#                         f"🗑️ Удаляем старую папку: {folder} (дата {folder_date.strftime('%d.%m.%Y')} старше {cutoff_date.strftime('%d.%m.%Y')})")
#                     shutil.rmtree(folder)
#                 else:
#                     print(f"✅ Сохраняем папку: {folder} (дата {folder_date.strftime('%d.%m.%Y')})")
#             except ValueError:
#                 print(f"⚠️ Пропускаем папку {folder.name}: не удалось извлечь дату из имени или неверный формат.")
#             except Exception as e:
#                 print(f"❌ Ошибка при удалении папки {folder.name}: {e}")
#     print(f"Очистка в {base_dir} завершена.")
#
#
# def send_all_analyses_to_integrations(analyses_folder_path: Path, target_folder_date_str: str):
#     """
#     Обрабатывает сгенерированные JSON-файлы анализов
#     и отправляет их в Google Forms. Предполагается, что отправка в Telegram
#     происходит из модуля google_sheets или его зависимостей.
#     """
#     print("\n--- Отправка анализов в Google Forms (и Telegram, если настроено в google_sheets) ---")
#
#     if not analyses_folder_path.exists():
#         print(f"Папка с анализами не найдена: {analyses_folder_path}. Пропускаем отправку.")
#         return
#
#     print(f"\n  ➡️ Запускаем отправку всех целевых анализов в Google Forms из {analyses_folder_path}.")
#     send_analyses_to_google_form(analyses_folder_path, target_folder_date_str)
#
#
# def run_processing_pipeline():
#     """
#     Определяет текущий временной диапазон для обработки звонков
#     на основе текущего времени по МСК и запускает пайплайн.
#     """
#     current_time_msk = datetime.now(MSK)
#     current_hour_msk = current_time_msk.hour
#     current_date_msk = current_time_msk.date()
#
#     print(f"Текущее время по МСК: {current_time_msk.strftime('%Y-%m-%d %H:%M:%S')}")
#
#     # Очищаем старые папки
#     clean_old_folders(Path("audio"), 1)
#     clean_old_folders(Path("transcripts"), 1)
#     clean_old_folders(Path("analyses"), 1)
#
#     start_time_period = None
#     end_time_period = None
#     target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#
#     # Определение периодов обработки по времени суток
#     if current_hour_msk == 12:
#         yesterday_date_msk = current_date_msk - timedelta(days=1)
#         print("Определен период обработки: утренние звонки (с вечера вчера до полудня сегодня)")
#         start_time_period = datetime.combine(yesterday_date_msk, datetime.min.time().replace(hour=19), tzinfo=MSK)
#         end_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=11, minute=59, second=59),
#                                            tzinfo=MSK)
#         target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#
#     elif current_hour_msk == 15: # ИСПРАВЛЕНО: Было 17, теперь 15, чтобы соответствовать описанию
#         print("Определен период обработки: дневные звонки (с полудня сегодня до 15:00 сегодня)")
#         start_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=12), tzinfo=MSK)
#         end_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=14, minute=59, second=59),
#                                            tzinfo=MSK)
#         target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#
#     elif current_hour_msk == 19:
#         print("Определен период обработки: вечерние звонки (с 15:00 сегодня до 19:00 сегодня)")
#         start_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=15), tzinfo=MSK)
#         end_time_period = datetime.combine(current_time_msk, datetime.min.time().replace(hour=18, minute=59, second=59),
#                                            tzinfo=MSK)
#         target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#     else:
#         # Эта ветка будет вызываться, если cron запустит скрипт не в 12, 15 или 19 часов.
#         # Например, если вы запустите скрипт вручную в другое время.
#         print(
#             "Текущее время не соответствует запланированным периодам обработки (12:00, 15:00, 19:00 МСК). Пропускаю выполнение.")
#         return # Важно: если время не подходит, просто выходим из функции
#
#     if start_time_period and end_time_period:
#         print(
#             f"Обработка звонков за период: {start_time_period.strftime('%Y-%m-%d %H:%M:%S')} - {end_time_period.strftime('%Y-%m-%d %H:%M:%S')}")
#         print(f"Целевая дата папок для обработки: {target_folder_date_str}")
#
#         # 1. Загрузка звонков
#         print("\n--- Загрузка звонков ---")
#         download_calls(start_time_period, end_time_period)
#         audio_dir = Path("audio") / f"звонки_{target_folder_date_str}"
#         print(f"Статус папки аудио: {audio_dir.exists()} (содержит {len(list(audio_dir.glob('*.mp3')))} mp3 файлов)")
#
#         # 2. Транскрибация звонков (всех загруженных)
#         print("\n--- Транскрибация звонков ---")
#         transcribe_all(target_folder_date_str, assign_roles=True)
#         transcripts_dir = Path("transcripts") / f"транскрибация_{target_folder_date_str}"
#         print(f"Статус папки транскриптов: {transcripts_dir.exists()} (содержит {len(list(transcripts_dir.glob('*.txt')))} txt файлов)")
#
#         # 3. Анализ транскриптов (analyzer.py сам решит, какие сохранять)
#         print("\n--- Анализ транскриптов ---")
#         analyze_transcripts(target_folder_date_str)
#         analyses_dir = Path("analyses") / f"транскрибация_{target_folder_date_str}"
#         print(f"Статус папки анализов: {analyses_dir.exists()} (содержит {len(list(analyses_dir.glob('*_analysis.json')))} json файлов)")
#
#         # 4. Отправка анализов в Google Forms (и Telegram, если настроено в google_sheets)
#         send_all_analyses_to_integrations(analyses_dir, target_folder_date_str)
#
#     print("\n✅ Пайплайн обработки звонков завершен.")
#
#
# if __name__ == "__main__":
#     print("🚀 Запуск пайплайна...")
#     run_processing_pipeline()
#     print("\n✅ Скрипт успешно завершил работу.")















# import os
# import sys
# import shutil
# import json
# from datetime import datetime, timedelta, timezone
# from pathlib import Path
# import re
# import time
#
# # Добавляем корневую директорию проекта в sys.path, если она еще не там.
# project_root = Path(__file__).resolve().parent
# if str(project_root) not in sys.path:
#     sys.path.append(str(project_root))
#
# # Импортируем необходимые модули
# from uis_call_downloader import download_calls, MSK
# from transcriber import transcribe_all
# from analyzer import analyze_transcripts
# from google_sheets import send_analyses_to_google_form
#
# def clean_old_folders(base_dir: Path, days_to_keep: int):
#     """
#     Удаляет папки в указанной базовой директории, если их дата старше,
#     чем days_to_keep дней (считая по дате в названии папки).
#     """
#     print(f"\n🧹 Запускаем очистку старых папок в {base_dir} (сохраняем за последние {days_to_keep} дней)...")
#
#     current_time_msk = datetime.now(MSK)
#     cutoff_date = (current_time_msk - timedelta(days=days_to_keep)).date()
#
#     if not base_dir.exists():
#         print(f"Директория {base_dir} не существует. Пропускаем очистку.")
#         return
#
#     for folder in base_dir.iterdir():
#         if folder.is_dir():
#             try:
#                 date_str_part = folder.name.split('_')[-1]
#                 folder_date = datetime.strptime(date_str_part, "%d.%m.%Y").date()
#
#                 if folder_date < cutoff_date:
#                     print(
#                         f"🗑️ Удаляем старую папку: {folder} (дата {folder_date.strftime('%d.%m.%Y')} старше {cutoff_date.strftime('%d.%m.%Y')})")
#                     shutil.rmtree(folder)
#                 else:
#                     print(f"✅ Сохраняем папку: {folder} (дата {folder_date.strftime('%d.%m.%Y')})")
#             except ValueError:
#                 print(f"⚠️ Пропускаем папку {folder.name}: не удалось извлечь дату из имени или неверный формат.")
#             except Exception as e:
#                 print(f"❌ Ошибка при удалении папки {folder.name}: {e}")
#     print(f"Очистка в {base_dir} завершена.")
#
#
# def send_all_analyses_to_integrations(analyses_folder_path: Path, target_folder_date_str: str):
#     """
#     Обрабатывает сгенерированные JSON-файлы анализов
#     и отправляет их в Google Forms. Предполагается, что отправка в Telegram
#     происходит из модуля google_sheets или его зависимостей.
#     """
#     print("\n--- Отправка анализов в Google Forms (и Telegram, если настроено в google_sheets) ---")
#
#     if not analyses_folder_path.exists():
#         print(f"Папка с анализами не найдена: {analyses_folder_path}. Пропускаем отправку.")
#         return
#
#     print(f"\n  ➡️ Запускаем отправку всех целевых анализов в Google Forms из {analyses_folder_path}.")
#     send_analyses_to_google_form(analyses_folder_path, target_folder_date_str)
#
#
# def run_processing_pipeline():
#     """
#     Определяет текущий временной диапазон для обработки звонков
#     на основе текущего времени по МСК и запускает пайплайн.
#     """
#     current_time_msk = datetime.now(MSK)
#     current_hour_msk = current_time_msk.hour
#     current_date_msk = current_time_msk.date()
#
#     print(f"Текущее время по МСК: {current_time_msk.strftime('%Y-%m-%d %H:%M:%S')}")
#
#     clean_old_folders(Path("audio"), 2)
#     clean_old_folders(Path("transcripts"), 2)
#     clean_old_folders(Path("analyses"), 2)
#
#     start_time_period = None
#     end_time_period = None
#     target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#
#     # Определение периодов обработки по времени суток
#     if current_hour_msk == 12:
#         yesterday_date_msk = current_date_msk - timedelta(days=1)
#         print("Определен период обработки: утренние звонки (с вечера вчера до полудня сегодня)")
#         start_time_period = datetime.combine(yesterday_date_msk, datetime.min.time().replace(hour=19), tzinfo=MSK)
#         end_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=11, minute=59, second=59),
#                                            tzinfo=MSK)
#         target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#
#     elif current_hour_msk == 15:
#         print("Определен период обработки: дневные звонки (с полудня сегодня до 15:00 сегодня)")
#         start_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=12), tzinfo=MSK)
#         end_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=14, minute=59, second=59),
#                                            tzinfo=MSK)
#         target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#
#     elif current_hour_msk == 19:
#         print("Определен период обработки: вечерние звонки (с 15:00 сегодня до 19:00 сегодня)")
#         start_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=15), tzinfo=MSK)
#         end_time_period = datetime.combine(current_time_msk, datetime.min.time().replace(hour=18, minute=59, second=59),
#                                            tzinfo=MSK)
#         target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")
#     else:
#         print(
#             "Текущее время не соответствует запланированным периодам обработки (12:00, 15:00, 19:00 МСК). Пропускаю выполнение.")
#         return # Важно: если время не подходит, просто выходим из функции
#
#     if start_time_period and end_time_period:
#         print(
#             f"Обработка звонков за период: {start_time_period.strftime('%Y-%m-%d %H:%M:%S')} - {end_time_period.strftime('%Y-%m-%d %H:%M:%S')}")
#         print(f"Целевая дата папок для обработки: {target_folder_date_str}")
#
#         # 1. Загрузка звонков
#         print("\n--- Загрузка звонков ---")
#         download_calls(start_time_period, end_time_period)
#         audio_dir = Path("audio") / f"звонки_{target_folder_date_str}"
#         print(f"Статус папки аудио: {audio_dir.exists()} (содержит {len(list(audio_dir.glob('*.mp3')))} mp3 файлов)")
#
#
#         # 2. Транскрибация звонков (всех загруженных)
#         print("\n--- Транскрибация звонков ---")
#         transcribe_all(target_folder_date_str, assign_roles=True)
#         transcripts_dir = Path("transcripts") / f"транскрибация_{target_folder_date_str}"
#         print(f"Статус папки транскриптов: {transcripts_dir.exists()} (содержит {len(list(transcripts_dir.glob('*.txt')))} txt файлов)")
#
#
#         # 3. Анализ транскриптов (analyzer.py сам решит, какие сохранять)
#         print("\n--- Анализ транскриптов ---")
#         analyze_transcripts(target_folder_date_str)
#         analyses_dir = Path("analyses") / f"транскрибация_{target_folder_date_str}"
#         print(f"Статус папки анализов: {analyses_dir.exists()} (содержит {len(list(analyses_dir.glob('*_analysis.json')))} json файлов)")
#
#
#         # 4. Отправка анализов в Google Forms (и Telegram, если настроено в google_sheets)
#         send_all_analyses_to_integrations(analyses_dir, target_folder_date_str)
#
#     print("\n✅ Пайплайн обработки звонков завершен.")
#
#
# if __name__ == "__main__":
#     print("🚀 Запуск скрипта в боевом режиме. Ожидание запланированных часов (12:00, 15:00, 19:00 МСК)...")
#     target_hours = [12, 15, 19] # Часы по МСК для запуска
#     last_run_date = None # Для отслеживания, чтобы сбрасывать состояние каждый день
#     hours_run_today = set() # Для отслеживания, какие часы уже были запущены сегодня
#
#     while True:
#         try:
#             current_time_msk = datetime.now(MSK)
#             current_hour_msk = current_time_msk.hour
#             current_date_msk = current_time_msk.date()
#
#             # Сброс состояния для нового дня
#             if last_run_date is None or current_date_msk > last_run_date:
#                 hours_run_today.clear()
#                 last_run_date = current_date_msk
#                 print(f"\n--- Новый день: {last_run_date.strftime('%d.%m.%Y')}. Состояние сброшено. ---")
#
#             if current_hour_msk in target_hours and current_hour_msk not in hours_run_today:
#                 print(f"\n--- Обнаружено запланированное время ({current_hour_msk}:00 МСК). Запускаем пайплайн... ---")
#                 run_processing_pipeline()
#                 hours_run_today.add(current_hour_msk)
#                 print(f"✅ Пайплайн успешно завершен для {current_hour_msk}:00 МСК.")
#             else:
#                 # Печатать статус каждые 10 минут, чтобы видеть, что скрипт работает
#                 if current_time_msk.minute % 10 == 0 and current_time_msk.second < 5:
#                     next_runs = sorted(list(set(target_hours) - hours_run_today))
#                     if next_runs:
#                         print(f"[{current_time_msk.strftime('%H:%M:%S')}] Ожидание запланированного времени. Следующие запуски: {next_runs} МСК.")
#                     else:
#                         print(f"[{current_time_msk.strftime('%H:%M:%S')}] Ожидание запланированного времени. Все запуски на сегодня завершены.")
#
#
#             # Задержка перед следующей проверкой
#             time.sleep(60) # Проверяем каждую минуту
#
#         except Exception as e:
#             print(f"❌ Критическая ошибка в основном цикле: {e}")
#             print("Попытка продолжить работу после 60 секунд...")
#             time.sleep(60) # Пауза перед попыткой продолжить