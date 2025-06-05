from transcriber import transcribe_all
from analyzer import analyze_transcripts
from google_sheets import send_analyses_to_google_form
from datetime import datetime


def main():
    # Транскрибация всех аудио с назначением ролей
    transcribe_all(assign_roles=True)

    # Получаем сегодняшнюю дату в формате дд.мм.гггг
    today_str = datetime.today().strftime("%d.%m.%Y")

    # Путь к папке с транскриптами на сегодня
    transcripts_folder = f"transcripts/транскрибация_{today_str}"

    # Анализ транскриптов звонков
    analyze_transcripts(transcripts_folder)

    # Отправка данных в Google Sheets
    analyses_folder = f"analyses/транскрибация_{today_str}"
    send_analyses_to_google_form(analyses_folder)


if __name__ == "__main__":
    main()
