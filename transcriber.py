import os
import openai
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Загрузка API-ключа из .env
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

AUDIO_DIR = Path("audio")
TRANSCRIPTS_DIR = Path("transcripts")


def transcribe_file(mp3_path: Path, transcript_path: Path, assign_roles=False) -> str:
    try:
        with mp3_path.open("rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        text = transcript.strip()

        if assign_roles:
            role_prompt = (
                    "Раздели следующий текст звонка на реплики Менеджера и Клиента, добавь подписи в начале каждой реплики, "
                    "например:\nМенеджер: Здравствуйте! Чем могу помочь?\nКлиент: Я хотел бы купить растение.\n\n"
                    "Текст звонка:\n" + text
            )
            chat_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты помощник, разделяющий роли в звонке."},
                    {"role": "user", "content": role_prompt}
                ],
                temperature=0
            )
            text = chat_response.choices[0].message.content.strip()

        with transcript_path.open("w", encoding="utf-8") as f:
            f.write(text)

        return text
    except Exception as e:
        error_text = f"[Ошибка транскрибации]: {e}"
        with transcript_path.open("w", encoding="utf-8") as f:
            f.write(error_text)
        return error_text


def transcribe_all(assign_roles=False):
    today = datetime.now().astimezone().strftime("%d.%m.%Y")
    today_folder_name = f"звонки_{today}"
    today_dir = AUDIO_DIR / today_folder_name
    transcript_dir = TRANSCRIPTS_DIR / f"транскрибация_{today}"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    call_counter = {}

    if not today_dir.exists():
        print(f"Папка с аудиофайлами на сегодня не найдена: {today_dir}")
        return

    for mp3_file in sorted(today_dir.glob("*.mp3")):
        base_name = mp3_file.stem
        n = call_counter.get(base_name, 1)

        while True:
            transcript_path = transcript_dir / f"call{n}.txt"
            if not transcript_path.exists():
                break
            n += 1

        call_counter[base_name] = n + 1
        print(f"Обработка {mp3_file.name} → {transcript_path.name}")
        transcribe_file(mp3_file, transcript_path, assign_roles=assign_roles)
