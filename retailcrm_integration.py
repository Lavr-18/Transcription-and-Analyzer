import os
import json
import requests
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

RETAILCRM_URL = "https://tropichouse.retailcrm.ru"
RETAILCRM_API_KEY = os.getenv("RETAILCRM_API_KEY")


def normalize_phone(phone_str: str) -> str:
    """
    Нормализует номер телефона к формату '7XXXXXXXXXX' (только цифры).
    Удаляет все нецифровые символы и заменяет начальную '8' на '7'.
    """
    digits_only = re.sub(r'\D', '', phone_str)
    if digits_only.startswith('8') and len(digits_only) == 11:
        return '7' + digits_only[1:]
    elif digits_only.startswith('7') and len(digits_only) == 11:
        return digits_only
    # Дополнительная обработка, если номер начинается с 9 и имеет 10 цифр (российские мобильные)
    elif digits_only.startswith('9') and len(digits_only) == 10:
        return '7' + digits_only
    return digits_only


def get_all_order_status_groups() -> list:
    """
    Получает список всех возможных групп статусов заказов из RetailCRM.
    Эта функция больше не используется для фильтрации заказов, но может быть полезной для отладки.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден. Невозможно получить группы статусов.")
        return []

    status_groups_api_endpoint = f"{RETAILCRM_URL}/api/v5/reference/status-groups"
    status_groups_params = {
        "apiKey": RETAILCRM_API_KEY
    }

    try:
        response = requests.get(status_groups_api_endpoint, params=status_groups_params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("success") and data.get("statusGroups"):
            group_codes = [group.get("code") for group in data["statusGroups"].values() if group.get("code")]
            return group_codes
        else:
            print("ℹ️ Не удалось получить группы статусов заказов из RetailCRM.")
            return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка при получении групп статусов из RetailCRM: {e}")
        return []
    except Exception as e:
        print(f"❌ Непредвиденная ошибка при получении групп статусов: {e}")
        return []


def get_customer_card_link_by_phone(phone_number: str) -> str:
    """
    Ищет клиента в RetailCRM по номеру телефона и возвращает ссылку на его карточку.

    Args:
        phone_number: Номер телефона клиента (например, "79851234567").

    Returns:
        Строка с URL карточки клиента в RetailCRM, или пустая строка, если клиент не найден или произошла ошибка.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден в .env. Невозможно подключиться к RetailCRM.")
        return ""

    # 1. Нормализуем входящий номер телефона
    normalized_input_phone = normalize_phone(phone_number)

    # Шаг 1: Ищем клиента по номеру телефона
    customers_api_endpoint = f"{RETAILCRM_URL}/api/v5/customers"
    customers_params = {
        "apiKey": RETAILCRM_API_KEY,
        "filter[phone]": normalized_input_phone  # Используем нормализованный номер
    }

    print(f"🔍 Ищем клиента в RetailCRM для номера: {normalized_input_phone}...")

    try:
        customers_response = requests.get(customers_api_endpoint, params=customers_params, timeout=10)
        customers_response.raise_for_status()
        customers_data = customers_response.json()

        print(f"DEBUG: Customers API Response Status Code: {customers_response.status_code}")
        print(
            f"DEBUG: Customers API Response Body (partial): {json.dumps(customers_data, indent=2, ensure_ascii=False)[:1000]}...")

        if customers_data.get("success") and customers_data.get("customers"):
            first_customer = customers_data["customers"][0]
            customer_id = first_customer.get("id")
            if customer_id:
                # Изменено: теперь ссылка включает якорь #t-log-orders
                customer_card_link = f"{RETAILCRM_URL}/customers/{customer_id}#t-log-orders"
                print(f"✅ Клиент найден. ID клиента: {customer_id}. Ссылка на карточку: {customer_card_link}")
                return customer_card_link
            else:
                print(f"ℹ️ Клиент найден, но не удалось извлечь ID.")
                return ""
        else:
            print(f"ℹ️ Клиент для номера {normalized_input_phone} не найден в RetailCRM.")
            return ""

    except requests.exceptions.HTTPError as http_err:
        print(
            f"❌ HTTP ошибка при запросе к RetailCRM (customers): {http_err} (Статус: {customers_response.status_code}, Ответ: {customers_response.text})")
        return ""
    except requests.exceptions.ConnectionError as conn_err:
        print(f"❌ Ошибка соединения с RetailCRM (customers): {conn_err}")
        return ""
    except requests.exceptions.Timeout as timeout_err:
        print(f"❌ Таймаут при ожидании ответа от RetailCRM (customers): {timeout_err}")
        return ""
    except Exception as e:
        print(f"❌ Непредвиденная ошибка при поиске клиента в RetailCRM: {e}")
        return ""


if __name__ == "__main__":
    # Пример использования (для тестирования модуля отдельно)
    test_phone = "79999928883"
    print(f"\n--- Тестирование get_customer_card_link_by_phone с номером {test_phone} ---")
    link = get_customer_card_link_by_phone(test_phone)
    if link:
        print(f"Результат теста: Ссылка на карточку клиента: {link}")
    else:
        print(f"Результат теста: Ссылка на карточку клиента не найдена.")

    print(f"\n--- Тестирование get_customer_card_link_by_phone с номером 79162002520 ---")
    test_phone_2 = "79162002520"
    link_2 = get_customer_card_link_by_phone(test_phone_2)
    if link_2:
        print(f"Результат теста: Ссылка на карточку клиента: {link_2}")
    else:
        print(f"Результат теста: Ссылка на карточку клиента не найдена.")
