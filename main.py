import os
import shutil  # Импортируем shutil для удаления папок
from pathlib import Path
from datetime import datetime, timedelta

from transcriber import transcribe_all
from analyzer import analyze_transcripts
from google_sheets import send_analyses_to_google_form
from uis_call_downloader import download_calls


def clean_old_files(base_dir: Path, prefix: str, days_old: int = 2):
    """
    Удаляет папки с данными старше указанного количества дней.
    Папка определяется по дате в её названии.

    :param base_dir: Базовая директория (например, 'audio', 'transcripts', 'analyses').
    :param prefix: Префикс имени папки, перед датой (например, 'звонки_', 'транскрибация_').
    :param days_old: Количество дней, после которых папка считается старой и подлежит удалению.
    """
    # Определяем пороговую дату. Все папки, чья дата создания раньше этой, будут удалены.
    threshold_date = datetime.now().astimezone() - timedelta(days=days_old)

    # Проверяем, существует ли базовая директория
    if not base_dir.exists():
        print(f"Директория {base_dir} не найдена. Пропуск очистки.")
        return

    print(f"Начало очистки в директории: {base_dir}")
    for folder in base_dir.iterdir():
        if folder.is_dir() and folder.name.startswith(prefix):
            try:
                # Извлекаем строку даты из имени папки (например, "ДД.ММ.ГГГГ")
                date_str = folder.name.replace(prefix, "")
                # Преобразуем строку даты в объект datetime для сравнения
                folder_date = datetime.strptime(date_str, "%d.%m.%Y").astimezone()

                # Сравниваем дату папки с пороговой датой
                if folder_date < threshold_date:
                    print(f"🗑️ Удаление старой папки: {folder}")
                    shutil.rmtree(folder)  # Удаляем папку и все её содержимое
                else:
                    print(f"✅ Папка {folder.name} не старее {days_old} дней. Пропуск.")
            except ValueError:
                # Если имя папки не соответствует ожидаемому формату даты
                print(f"⚠️ Не удалось разобрать дату из имени папки: {folder.name}. Пропуск.")
            except Exception as e:
                # Общая ошибка при удалении папки
                print(f"❌ Ошибка при удалении папки {folder.name}: {e}")
    print(f"Очистка в директории {base_dir} завершена.")


def main():
    # --- Запуск очистки старых файлов перед новой обработкой ---
    print("\n--- Запуск процедуры очистки старых файлов (старше 2 дней) ---")
    clean_old_files(Path("audio"), "звонки_")
    clean_old_files(Path("transcripts"), "транскрибация_")
    clean_old_files(Path("analyses"), "транскрибация_")
    print("--- Процедура очистки завершена ---\n")

    # Скачиваем звонки за вчера
    download_calls()

    # Транскрибация всех аудио с назначением ролей
    transcribe_all(assign_roles=True)

    # Получаем вчерашнюю дату в формате дд.мм.гггг
    yesterday_str = (datetime.now().astimezone() - timedelta(days=1)).strftime("%d.%m.%Y")

    # Путь к папке с транскриптами на вчера
    transcripts_folder = Path("transcripts") / f"транскрибация_{yesterday_str}"

    # Анализ транскриптов звонков
    analyze_transcripts(transcripts_folder)

    # Отправка данных в Google Sheets
    analyses_folder = Path("analyses") / f"транскрибация_{yesterday_str}"
    send_analyses_to_google_form(analyses_folder)


if __name__ == "__main__":
    main()
