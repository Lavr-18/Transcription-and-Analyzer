import sys
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем корневую директорию проекта в sys.path, если она еще не там.
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# Импортируем необходимые модули
# Предполагается, что эти файлы существуют и содержат необходимые функции
from uis_call_downloader import download_calls, MSK
from transcriber import transcribe_all
from analyzer import analyze_transcripts
from google_sheets import send_analyses_to_google_form


def clean_old_folders(base_dir: Path, days_to_keep: int):
    """
    Удаляет папки в указанной базовой директории, если их дата старше,
    чем days_to_keep дней (считая по дате в названии папки).
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
                # Извлекаем дату из имени папки, например "звонки_07.08.2025"
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
    Обрабатывает сгенерированные JSON-файлы анализов
    и отправляет их в Google Forms. Предполагается, что отправка в Telegram
    происходит из модуля google_sheets или его зависимостей.
    """
    print("\n--- Отправка анализов в Google Forms (и Telegram, если настроено в google_sheets) ---")

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

    # Определение периодов обработки по времени суток
    if current_hour_msk == 12:
        yesterday_date_msk = current_date_msk - timedelta(days=1)
        print("Определен период обработки: утренние звонки (с вечера вчера до полудня сегодня)")
        start_time_period = datetime.combine(yesterday_date_msk, datetime.min.time().replace(hour=19), tzinfo=MSK)
        end_time_period = datetime.combine(current_date_msk, datetime.min.time().replace(hour=11, minute=59, second=59),
                                           tzinfo=MSK)
        target_folder_date_str = current_date_msk.strftime("%d.%m.%Y")

    elif current_hour_msk == 15:  # ИСПРАВЛЕНО: Было 17, теперь 15, чтобы соответствовать описанию
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
        # Эта ветка будет вызываться, если cron запустит скрипт не в 12, 15 или 19 часов.
        # Например, если вы запустите скрипт вручную в другое время.
        print(
            "Текущее время не соответствует запланированным периодам обработки (12:00, 15:00, 19:00 МСК). Пропускаю выполнение.")
        return  # Важно: если время не подходит, просто выходим из функции

    if start_time_period and end_time_period:
        print(
            f"Обработка звонков за период: {start_time_period.strftime('%Y-%m-%d %H:%M:%S')} - {end_time_period.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Целевая дата папок для обработки: {target_folder_date_str}")

        # 1. Загрузка звонков
        print("\n--- Загрузка звонков ---")
        download_calls(start_time_period, end_time_period)
        audio_dir = Path("audio") / f"звонки_{target_folder_date_str}"
        print(f"Статус папки аудио: {audio_dir.exists()} (содержит {len(list(audio_dir.glob('*.mp3')))} mp3 файлов)")

        # 2. Транскрибация звонков (всех загруженных)
        print("\n--- Транскрибация звонков ---")
        transcribe_all(target_folder_date_str, assign_roles=True)
        transcripts_dir = Path("transcripts") / f"транскрибация_{target_folder_date_str}"
        print(
            f"Статус папки транскриптов: {transcripts_dir.exists()} (содержит {len(list(transcripts_dir.glob('*.txt')))} txt файлов)")

        # 3. Анализ транскриптов (analyzer.py сам решит, какие сохранять)
        print("\n--- Анализ транскриптов ---")
        analyze_transcripts(target_folder_date_str)
        analyses_dir = Path("analyses") / f"транскрибация_{target_folder_date_str}"
        print(
            f"Статус папки анализов: {analyses_dir.exists()} (содержит {len(list(analyses_dir.glob('*_analysis.json')))} json файлов)")

        # 4. Отправка анализов в Google Forms (и Telegram, если настроено в google_sheets)
        send_all_analyses_to_integrations(analyses_dir, target_folder_date_str)

    print("\n✅ Пайплайн обработки звонков завершен.")


if __name__ == "__main__":
    print("🚀 Запуск пайплайна...")
    run_processing_pipeline()
    print("\n✅ Скрипт успешно завершил работу.")
