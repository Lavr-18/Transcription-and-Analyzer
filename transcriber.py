import os
import openai
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI

# Загрузка API-ключа из .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Определение директорий для аудио и транскриптов
AUDIO_DIR = Path("audio")
TRANSCRIPTS_DIR = Path("transcripts")


def transcribe_file(mp3_path: Path, transcript_path: Path, assign_roles=False) -> str:
    """
    Транскрибирует аудиофайл MP3 в текстовый файл.
    При необходимости может разделять реплики на Менеджера и Клиента.
    """
    try:
        # Открываем аудиофайл в бинарном режиме
        with mp3_path.open("rb") as audio_file:
            # Отправляем аудиофайл в Whisper API для транскрибации
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text" # Получаем ответ в виде простого текста
            )
        text = transcript.strip() # Удаляем лишние пробелы в начале и конце

        if assign_roles:
            # Если требуется разделение ролей, формируем промпт для GPT
            # Улучшенный промпт для более точного разделения ролей:
            role_prompt = (
                "Ты - транскрибатор, твоя задача - взять предоставленный текст телефонного разговора "
                "и распределить каждую реплику между двумя участниками: 'Менеджер' и 'Клиент'. "
                "Обязательно сохраняй полный оригинальный текст каждой реплики, не сокращай и не перефразируй. "
                "Каждая реплика должна начинаться с 'Менеджер:' или 'Клиент:', после чего следует текст реплики. "
                "Каждая реплика должна быть на новой строке. "
                "Не добавляй никаких дополнительных комментариев, вступлений или заключений. "
                "Просто предоставь диалог в указанном формате."
                "\n\nПример ожидаемого формата:\n"
                "Менеджер: Здравствуйте! Чем могу помочь?\n"
                "Клиент: Я хотел бы купить растение.\n"
                "Менеджер: Отлично, у нас большой выбор.\n"
                "Клиент: Расскажите подробнее.\n\n"
                "Текст звонка для разделения:\n" + text
            )
            # Отправляем текст звонка в GPT для разделения ролей
            chat_response = client.chat.completions.create(
                model="gpt-4o", # Используем модель GPT-4o
                messages=[
                    {"role": "system", "content": "Ты высокоточный эксперт по разделению ролей в телефонных звонках. Твоя цель - идеально разделить диалог на реплики Менеджера и Клиента, строго следуя инструкциям пользователя и не добавляя ничего лишнего."},
                    {"role": "user", "content": role_prompt}
                ],
                temperature=0 # Устанавливаем температуру 0 для более детерминированного ответа
            )
            text = chat_response.choices[0].message.content.strip() # Обновляем текст с разделенными ролями

        # Записываем транскрибированный текст в файл
        with transcript_path.open("w", encoding="utf-8") as f:
            f.write(text)

        return text
    except Exception as e:
        # В случае ошибки транскрибации, записываем сообщение об ошибке в файл транскрипта
        error_text = f"[Ошибка транскрибации]: {e}"
        with transcript_path.open("w", encoding="utf-8") as f:
            f.write(error_text)
        return error_text


def transcribe_all(assign_roles=False):
    """
    Транскрибирует все MP3-файлы за вчерашний день.
    """
    # Получаем вчерашнюю дату в формате дд.мм.гггг
    yesterday = (datetime.now().astimezone() - timedelta(days=1)).strftime("%d.%m.%Y")
    yesterday_folder_name = f"звонки_{yesterday}"
    audio_dir = AUDIO_DIR / yesterday_folder_name # Путь к папке с аудиофайлами за вчера
    transcript_dir = TRANSCRIPTS_DIR / f"транскрибация_{yesterday}" # Путь к папке для транскриптов
    transcript_dir.mkdir(parents=True, exist_ok=True) # Создаем папку, если ее нет

    if not audio_dir.exists():
        print(f"Папка с аудиофайлами за вчера не найдена: {audio_dir}")
        return

    # Итерируем по всем MP3-файлам в отсортированном порядке
    for mp3_file in sorted(audio_dir.glob("*.mp3")):
        # Используем имя файла MP3 (без расширения) для имени файла транскрипта.
        # Это гарантирует, что call1.mp3 -> call1.txt, call6.mp3 -> call6.txt и т.д.
        transcript_path = transcript_dir / f"{mp3_file.stem}.txt"

        # Проверяем, существует ли уже транскрипт, чтобы избежать повторной обработки
        if transcript_path.exists():
            print(f"Пропуск {mp3_file.name} - транскрипт уже существует как {transcript_path.name}")
            continue

        print(f"Обработка {mp3_file.name} → {transcript_path.name}")
        # Вызываем функцию транскрибации для каждого файла
        transcribe_file(mp3_file, transcript_path, assign_roles=assign_roles)

