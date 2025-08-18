import os
import requests
import re
from dotenv import load_dotenv

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


def get_order_link_by_phone(phone_number: str) -> str:
    """
    Ищет заказы в RetailCRM по номеру телефона.
    Сначала пытается найти прямой заказ, если не находит - возвращает ссылку на карточку клиента.

    Args:
        phone_number: Номер телефона клиента (например, "79851234567").

    Returns:
        Строка с URL заказа в RetailCRM, или URL карточки клиента, или пустая строка, если ничего не найдено.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден в .env. Невозможно подключиться к RetailCRM.")
        return ""

    normalized_input_phone = normalize_phone(phone_number)

    # --- Шаг 1: Ищем клиента по номеру телефона (используем filter[name]) ---
    customers_api_endpoint = f"{RETAILCRM_URL}/api/v5/customers"
    customers_params = {
        "apiKey": RETAILCRM_API_KEY,
        "filter[name]": normalized_input_phone  # ИСПРАВЛЕНО: Используем filter[name]
    }

    print(f"🔍 Шаг 1: Ищем клиента в RetailCRM для номера: {normalized_input_phone} (фильтр по имени)...")

    try:
        customers_response = requests.get(customers_api_endpoint, params=customers_params, timeout=10)
        customers_response.raise_for_status()
        data = customers_response.json()

        if data.get("success") and data.get("customers"):
            first_customer = data["customers"][0]
            customer_id = first_customer.get("id")
            if customer_id:
                # Генерируем ссылку на карточку клиента как запасной вариант
                customer_card_link = f"{RETAILCRM_URL}/customers/{customer_id}#t-log-orders"
                print(
                    f"✅ Шаг 1: Клиент найден. ID клиента: {customer_id}. Запасная ссылка на карточку: {customer_card_link}")
            else:
                print(f"ℹ️ Шаг 1: Клиент найден, но не удалось извлечь ID.")
                return ""  # Если ID клиента нет, то и заказы не найти
        else:
            print(f"ℹ️ Шаг 1: Клиент для номера {normalized_input_phone} не найден в RetailCRM.")
            return ""  # Если клиент не найден, то и заказы не найти

    except requests.exceptions.RequestException as e:
        print(f"❌ Шаг 1: Ошибка при поиске клиента в RetailCRM: {e}")
        return ""  # В случае ошибки возвращаем пустую строку

    # --- Шаг 2: Ищем заказы по ID клиента (упрощенный запрос) ---
    if customer_id:
        orders_api_endpoint = f"{RETAILCRM_URL}/api/v5/orders"
        orders_params = {
            "apiKey": RETAILCRM_API_KEY,
            "filter[customerId]": customer_id,  # Используем filter[customerId]
        }

        print(f"🔍 Шаг 2: Ищем заказы в RetailCRM для клиента ID: {customer_id} (упрощенный запрос)...")

        try:
            orders_response = requests.get(orders_api_endpoint, params=orders_params, timeout=10)
            orders_response.raise_for_status()
            orders_data = orders_response.json()

            if orders_data.get("success") and orders_data.get("orders"):
                # Сортируем заказы по дате создания в убывающем порядке, чтобы получить самый новый
                sorted_orders = sorted(orders_data["orders"], key=lambda x: x.get("createdAt", ""), reverse=True)
                first_order = sorted_orders[0]
                order_id = first_order.get("id")

                if order_id:
                    order_link = f"{RETAILCRM_URL}/orders/{order_id}/edit"
                    print(f"✅ Шаг 2: Найден прямой заказ. Ссылка на заказ: {order_link}")
                    return order_link  # Возвращаем прямую ссылку на заказ
                else:
                    print(f"ℹ️ Шаг 2: Заказ найден, но не удалось извлечь ID заказа.")
                    return customer_card_link  # Возвращаем запасную ссылку
            else:
                print(
                    f"ℹ️ Шаг 2: Заказы для клиента ID {customer_id} не найдены в RetailCRM. Возвращаем ссылку на карточку клиента.")
                return customer_card_link  # Если заказы не найдены, возвращаем запасную ссылку

        except requests.exceptions.RequestException as e:
            print(f"❌ Шаг 2: Ошибка при поиске заказа в RetailCRM: {e}. Возвращаем ссылку на карточку клиента.")
            return customer_card_link  # В случае ошибки возвращаем запасную ссылку
    else:
        print("ℹ️ Шаг 2 пропущен: ID клиента не был найден на Шаге 1.")
        return ""  # Если ID клиента не найден на Шаге 1, возвращаем пустую строку


def get_manager_name_from_crm(phone_number: str) -> str | None:
    """
    Ищет ответственного менеджера по последнему заказу клиента в RetailCRM по номеру телефона.

    Args:
        phone_number: Номер телефона клиента.

    Returns:
        Имя менеджера (firstName) или None, если менеджер не найден или произошла ошибка.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден в .env. Невозможно подключиться к RetailCRM.")
        return None

    normalized_phone = normalize_phone(phone_number)
    manager_id = None

    # --- Шаг 1: Ищем последний заказ по номеру телефона клиента (упрощенный запрос) ---
    # Согласно поддержке, для поиска заказов по номеру телефона клиента используем filter[customer]
    orders_api_endpoint = f"{RETAILCRM_URL}/api/v5/orders"
    orders_params = {
        "apiKey": RETAILCRM_API_KEY,
        "filter[customer]": normalized_phone,  # Используем filter[customer] с номером телефона
    }

    print(f"🔍 CRM-поиск менеджера: Ищем последний заказ для номера: {normalized_phone} (упрощенный запрос)...")

    try:
        orders_response = requests.get(orders_api_endpoint, params=orders_params, timeout=10)
        orders_response.raise_for_status()
        orders_data = orders_response.json()

        if orders_data.get("success") and orders_data.get("orders"):
            # Сортируем заказы по дате создания в убывающем порядке, чтобы получить самый новый
            sorted_orders = sorted(orders_data["orders"], key=lambda x: x.get("createdAt", ""), reverse=True)
            last_order = sorted_orders[0]
            manager_id = last_order.get("managerId")
            if manager_id:
                print(f"✅ CRM-поиск менеджера: Найден заказ с managerId: {manager_id}")
            else:
                print(f"ℹ️ CRM-поиск менеджера: Заказ найден, но managerId отсутствует.")
                return None
        else:
            print(f"ℹ️ CRM-поиск менеджера: Заказы для номера {normalized_phone} не найдены.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ CRM-поиск менеджера: Ошибка при поиске заказа: {e}")
        return None
    except Exception as e:
        print(f"❌ CRM-поиск менеджера: Непредвиденная ошибка при поиске заказа: {e}")
        return None

    # --- Шаг 2: Получаем имя менеджера по managerId ---
    if manager_id:
        # ИСПРАВЛЕНО: Изменен эндпоинт с /reference/users на /users
        users_api_endpoint = f"{RETAILCRM_URL}/api/v5/users"
        users_params = {
            "apiKey": RETAILCRM_API_KEY
        }

        print(f"🔍 CRM-поиск менеджера: Получаем информацию о пользователе с ID: {manager_id}...")

        try:
            users_response = requests.get(users_api_endpoint, params=users_params, timeout=10)
            users_response.raise_for_status()
            users_data = users_response.json()

            if users_data.get("success") and users_data.get("users"):
                # ИСПРАВЛЕНО: RetailCRM API /users возвращает список пользователей,
                # поэтому итерируем по списку, чтобы найти пользователя по ID.
                found_user = None
                for user_item in users_data["users"]:
                    if str(user_item.get("id")) == str(manager_id):
                        found_user = user_item
                        break

                if found_user:
                    manager_name = found_user.get("firstName")
                    if manager_name:
                        print(f"✅ CRM-поиск менеджера: Найдено имя менеджера: {manager_name}")
                        return manager_name
                    else:
                        print(f"ℹ️ CRM-поиск менеджера: Имя менеджера для ID {manager_id} не найдено.")
                        return None
                print(f"ℹ️ CRM-поиск менеджера: Пользователь с ID {manager_id} не найден в списке пользователей.")
                return None
            else:
                print("ℹ️ CRM-поиск менеджера: Не удалось получить список пользователей.")
                return None

        except requests.exceptions.RequestException as e:
            print(f"❌ CRM-поиск менеджера: Ошибка при получении списка пользователей: {e}")
            return None
        except Exception as e:
            print(f"❌ CRM-поиск менеджера: Непредвиденная ошибка при получении списка пользователей: {e}")
            return None
    return None


if __name__ == "__main__":
    test_phones = [
        "79166516536",
        "79160271945",
        "79854523727",
        "74992670385",
        "79852222666",
        "74993482193",
        "79855775960",
        "79257763463",
        "79067777466",
        "79067777466",
        "79267767176",
        "79857776565",
        "79362814549",
        "79265902643",
        "79257661800",
        "79684411994",
        "79684411994",
        "79161106668",  # Проблемный номер из переписки с поддержкой
        "79969795064",  # Проблемный номер
        "79037951801",  # Проблемный номер
        "79398538673",  # Проблемный номер
        "79685063717",  # Проблемный номер
        "74954017276"  # Проблемный номер
    ]
    links = []
    manager_names_from_crm = []

    for i, phone in enumerate(test_phones):
        print(f"\n--- Тестирование get_order_link_by_phone с номером {phone} (Тест {i + 1}/{len(test_phones)}) ---")
        link = get_order_link_by_phone(phone)
        links.append(link)
        if link:
            print(f"Результат теста: Ссылка: {link}")
        else:
            print(f"Результат теста: Ссылка не найдена.")

        print(f"--- Тестирование get_manager_name_from_crm с номером {phone} ---")
        manager_name = get_manager_name_from_crm(phone)
        manager_names_from_crm.append(manager_name)
        if manager_name:
            print(f"Результат теста: Менеджер из CRM: {manager_name}")
        else:
            print(f"Результат теста: Менеджер из CRM не найден.")

    print("\n--- Все найденные ссылки ---")
    print(*links, sep='\n')

    print("\n--- Все найденные менеджеры из CRM ---")
    print(*manager_names_from_crm, sep='\n')
