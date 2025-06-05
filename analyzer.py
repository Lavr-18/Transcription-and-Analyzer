import os
import json
import re
import time
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

CRITERIA = [
    "улыбка_в_голосе",
    "установление_контакта",
    "квалификация",
    "выявление_потребности",
    "пересогласование",
    "особенности_позиций",
    "возражение",
    "отработка_возражения",
    "докомплект",
    "допродажа",
    "состав_и_сумма",
    "согласование_деталей",
    "предоплата"
]

PROMPT_TEMPLATE = '''Ты опытный специалист по продажам, анализирующий звонки по чек-листу.

Ниже приведён текст диалога между Менеджером и Клиентом. Твоя задача — проанализировать его по определённым критериям и поставить оценку от -1 до 1 по каждому из них, где -1 - не выполнено, 0 - не применимо, 1 - выполнено. Пояснения не нужны.

Критерии:
1. Улыбка в голосе, энергичный тон  
2. Установление контакта (называть клиента по имени, комплименты, подтверждение правильности выбора)  
3. Квалификация (что нужно, когда, сроки, бюджет)  
4. Выявление потребности — какую проблему решает клиент (вопросы: размер, куда, покупаете впервые, прихотливость, уход)  
5. Пересогласование на основе выявленных потребностей — менеджер сам предложил готовое решение  
6. Проговорить особенности позиций (прихотливые растения, эксклюзивные)  
7. Возражение клиента — фраза  
8. Отработка возражения — фраза  
9. Предложить докомплект (кашпо + грунт + пересадка; растения; аксессуары)  
10. Предложить допродажу (удобрения, освещение, аксессуары)  
11. Проговорить состав заказа и общую сумму  
12. Согласовать детали (адрес; сроки доставки)  
13. Проговорить про предоплату по схеме: дедлайн + причина (например: «оплатите в течение часа, чтобы забронировать растение, потому что бирочки вешаем только после предоплаты»)

Ответ:
JSON формат, только числа -1, 0 или 1:

Пример:
{{
  "улыбка_в_голосе": 1,
  "установление_контакта": 1,
  "квалификация": 0,
  "выявление_потребности": 1,
  "пересогласование": 1,
  "особенности_позиций": 0,
  "возражение": -1,
  "отработка_возражения": 1,
  "докомплект": 0,
  "допродажа": 0,
  "состав_и_сумма": 1,
  "согласование_деталей": 1,
  "предоплата": 1
}}

Текст звонка:
"""
{transcript}
"""
'''


def clean_json_string(raw_content):
    match = re.search(r'{[\s\S]+}', raw_content)
    return match.group(0) if match else '{}'


def analyze_transcripts(transcripts_folder):
    output_folder = transcripts_folder.replace("transcripts", "analyses")
    os.makedirs(output_folder, exist_ok=True)

    for i, filename in enumerate(sorted(os.listdir(transcripts_folder))):
        if not filename.endswith(".txt"):
            continue

        path = os.path.join(transcripts_folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            transcript = f.read()

        prompt = PROMPT_TEMPLATE.format(transcript=transcript)

        success = False
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                raw_content = response.choices[0].message.content
                json_str = clean_json_string(raw_content)
                result_dict = json.loads(json_str)
                filtered_result = {key: result_dict.get(key, 0) for key in CRITERIA}
                success = True
                break
            except Exception as e:
                print(f"⚠️ Ошибка при генерации/парсинге (попытка {attempt + 1}): {e}")
                time.sleep(2)  # Задержка между попытками

        if not success:
            fail_path = os.path.join(output_folder, f"{filename.replace('.txt', '')}_raw.txt")
            with open(fail_path, "w", encoding="utf-8") as f:
                f.write(transcript)
            print(f"❌ Не удалось проанализировать: {filename} — результат сохранён")
            continue

        out_path = os.path.join(output_folder, f"{filename.replace('.txt', '')}_analysis.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(filtered_result, f, ensure_ascii=False, indent=2)

        print(f"✅ Анализ сохранён: {out_path}")


if __name__ == "__main__":
    today = datetime.today().strftime("%d.%m.%Y")
    folder_name = f"транскрибация_{today}"
    analyze_transcripts(f"transcripts/{folder_name}")
