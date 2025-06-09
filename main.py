from transcriber import transcribe_all
from analyzer import analyze_transcripts
from google_sheets import send_analyses_to_google_form
from uis_call_downloader import download_calls
from datetime import datetime, timedelta


def main():
    # Скачиваем звонки за вчера
    download_calls()

    # Транскрибация всех аудио с назначением ролей
    transcribe_all(assign_roles=True)

    # Получаем вчерашнюю дату в формате дд.мм.гггг
    yesterday_str = (datetime.now().astimezone() - timedelta(days=1)).strftime("%d.%m.%Y")

    # Путь к папке с транскриптами на вчера
    transcripts_folder = f"transcripts/транскрибация_{yesterday_str}"

    # Анализ транскриптов звонков
    analyze_transcripts(transcripts_folder)

    # Отправка данных в Google Sheets
    analyses_folder = f"analyses/транскрибация_{yesterday_str}"
    send_analyses_to_google_form(analyses_folder)


if __name__ == "__main__":
    main()
