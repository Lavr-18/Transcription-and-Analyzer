import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Ваш токен Telegram бота. Получите его у @BotFather в Telegram.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# ID чатов получателей (РОПов и других, кто "запускал").
# Это может быть список ID личных чатов или ID групп.
# Укажите их в файле .env через запятую, например: ROP_CHAT_IDS="123456789,987654321,-1234567890"
# Чтобы узнать ID личного чата, напишите что-нибудь боту и перейдите по ссылке:
# https://api.telegram.org/bot<ВАШ_ТОКЕН>/getUpdates
# В ответе найдите "chat":{"id": <ВАШ_CHAT_ID>...}
# Если это ID группы, он будет отрицательным.
ROP_CHAT_IDS_STR = os.getenv("ROP_CHAT_IDS")
ROP_CHAT_IDS = [chat_id.strip() for chat_id in ROP_CHAT_IDS_STR.split(',') if
                chat_id.strip()] if ROP_CHAT_IDS_STR else []


def send_telegram_message(message: str) -> bool:
    """
    Отправляет текстовое сообщение в Telegram бот каждому из списка получателей.

    Args:
        message: Текст сообщения для отправки.

    Returns:
        True, если хотя бы одно сообщение успешно отправлено, False в противном случае.
    """
    if not TELEGRAM_BOT_TOKEN:
        print("❗ Ошибка: TELEGRAM_BOT_TOKEN не найден в .env. Сообщения в Telegram не будут отправлены.")
        return False
    if not ROP_CHAT_IDS:
        print("❗ Ошибка: ROP_CHAT_IDS не найдены в .env или список пуст. Сообщения в Telegram не будут отправлены.")
        return False

    all_sent_successfully = True

    for chat_id in ROP_CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"  # Можно использовать "MarkdownV2" или "HTML" для форматирования
        }

        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()  # Вызывает исключение для HTTP ошибок (4xx или 5xx)
            response_json = response.json()

            if response_json.get("ok"):
                print(f"✅ Сообщение в Telegram успешно отправлено в чат ID: {chat_id}")
            else:
                print(
                    f"❌ Ошибка отправки в Telegram в чат ID: {chat_id} — {response_json.get('description', 'Неизвестная ошибка')}")
                all_sent_successfully = False  # Если хотя бы одно сообщение не отправлено, флаг меняется
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка сетевого запроса при отправке в Telegram в чат ID: {chat_id} — {e}")
            all_sent_successfully = False
        except Exception as e:
            print(f"❌ Непредвиденная ошибка при отправке в Telegram в чат ID: {chat_id} — {e}")
            all_sent_successfully = False

    return all_sent_successfully


if __name__ == "__main__":
    # Пример использования для тестирования модуля
    test_message = "<b>Тестовое резюме звонка:</b>\n" \
                   "<i>Это тестовое сообщение из скрипта.</i>\n" \
                   "Проверка отправки резюме в Telegram всем получателям. Работает!"

    print("\n--- Тестирование отправки сообщения в Telegram ---")
    success = send_telegram_message(test_message)
    if success:
        print("Все тестовые сообщения успешно отправлены.")
    else:
        print("Возникли ошибки при отправке тестовых сообщений.")