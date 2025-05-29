import os
import openai
from openai import OpenAI
from pathlib import Path

# Укажи свой API-ключ
client = OpenAI(api_key="sk-...")

# Папка с аудиофайлами
INPUT_DIR = Path("audio_input")
OUTPUT_DIR = Path("transcripts")
OUTPUT_DIR.mkdir(exist_ok=True)

# Поддерживаемые форматы: .mp3, .mp4, .mpeg, .mpga, .m4a, .wav, .webm
for file in INPUT_DIR.iterdir():
    if file.suffix.lower() not in [".mp3", ".wav", ".m4a", ".mp4", ".webm"]:
        continue

    print(f"🎙 Обработка: {file.name}")
    with open(file, "rb") as audio_file:
        try:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru"
            )
        except openai.APIError as e:
            print(f"❌ Ошибка API: {e}")
            continue

    out_path = OUTPUT_DIR / f"{file.stem}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(transcript.text)

    print(f"✅ Сохранено: {out_path}")
