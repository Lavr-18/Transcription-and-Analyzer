import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Загружаем переменные окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ROP_CHAT_IDS = os.getenv("ROP_CHAT_IDS", "").split(',')
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_TOPIC_ID = os.getenv("TELEGRAM_TOPIC_ID")


def send_telegram_message(message: str):
    """
    Отправляет HTML-сообщение в Telegram-чаты, указанные в .env.
    Теперь также поддерживает отправку в супергруппы с темами.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("❗ TELEGRAM_BOT_TOKEN не найден в .env. Отправка в Telegram невозможна.")
        return

    # Список получателей: основная супергруппа + отдельные чаты (если есть)
    recipients = []
    # Если указана супергруппа, добавляем её в список получателей
    if TELEGRAM_CHAT_ID:
        recipients.append({
            "chat_id": TELEGRAM_CHAT_ID,
            "topic_id": TELEGRAM_TOPIC_ID
        })
    # Добавляем чаты из ROP_CHAT_IDS, если они существуют
    if ROP_CHAT_IDS and ROP_CHAT_IDS[0]:
        for chat_id in ROP_CHAT_IDS:
            recipients.append({
                "chat_id": chat_id.strip(),
                "topic_id": None
            })

    # Отправляем сообщение каждому получателю
    for recipient in recipients:
        chat_id = recipient["chat_id"]
        topic_id = recipient["topic_id"]

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }

        # Добавляем message_thread_id только если topic_id существует
        if topic_id:
            payload["message_thread_id"] = topic_id

        try:
            response = requests.post(url, data=payload, timeout=10)
            response.raise_for_status()
            print(f"✅ Сообщение в Telegram успешно отправлено в чат ID: {chat_id}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка сетевого запроса при отправке в Telegram в чат ID: {chat_id} — {e}")


if __name__ == '__main__':
    # Пример использования для теста
    test_message = "<b>Тестовое сообщение из скрипта</b>\n\nПроверка отправки в Telegram."
    send_telegram_message(test_message)
