import os
import json
import requests
import re
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional  # Добавлены необходимые типы

load_dotenv()

RETAILCRM_URL = "https://tropichouse.retailcrm.ru"
RETAILCRM_API_KEY = os.getenv("RETAILCRM_API_KEY")

# --- НОВЫЕ СТАТУСЫ ДЛЯ АНАЛИЗА ---
# Объединяем статусы из групп "Новый", "Согласование", "Выполнен", "Отмена".
# Звонок подлежит анализу, если последний заказ в ОДНОМ из этих статусов, ИЛИ если заказов нет.
ANALYZABLE_STATUS_CODES = [
    # Группа "Новый" (new)
    "new", "gotovo-k-soglasovaniiu", "soglasovat-sostav", "agree-absence", "novyi-predoplachen", "novyi-oplachen",
    # Группа "Согласование" (approval)
    "availability-confirmed", "client-confirmed", "offer-analog", "ne-dozvonilis", "perezvonit-pozdnee",
    "otpravili-varianty-na-pochtu", "otpravili-varianty-v-vatsap", "ready-to-wait", "waiting-for-arrival",
    "klient-zhdet-foto-s-zakupki", "vizit-v-shourum", "ozhidaet-oplaty", "gotovim-kp", "kp-gotovo-k-zashchite",
    "soglasovanie-kp", "proekt-visiak", "soglasovano", "oplacheno", "prepayed", "soglasovan-ozhidaet-predoplaty",
    "vyezd-biologa-oplachen", "vyezd-biologa-zaplanirovano", "predoplata-poluchena", "oplata-ne-proshla",
    "proverka-nalichiia", "obsluzhivanie-zaplanirovano", "obsluzhivanie-soglasovanie", "predoplachen-soglasovanie",
    "servisnoe-obsluzhivanie-oplacheno", "zakaz-obrabotan-soglasovanie", "vyezd-biologa-soglasovanie",
    # Группа "Выполнен" (complete)
    "complete", "partially-completed", "frendli-zvonok-naznachen", "frendli-zvonok-sovershen",
    # Группа "Отменен" (cancel)
    "no-call", "no-product", "already-buyed", "delyvery-did-not-suit", "prices-did-not-suit", "return",
    "ne-khochet-vnosit-predoplatu", "klient-ne-vykhodit-na-sviaz", "nuzhno-srochno-no-storonnei-dostavkoi-ne-khotiat",
    "nuzhno-srochno-rasteniia-net-v-nalichii", "dostavka-v-drugoi-region-zhivoe-rastenie-melkii-zakaz",
    "ne-aktualno-uzhe-kupili-v-drugom-meste", "ne-aktualno-peredumali-darit-peredumali-pokupat-oformit-pozzhe",
    "net-v-nalichii-v-gollandii", "kashpo-net-v-nalichii-ne-khotiat-zhdat", "ne-khotiat-oplachivat-dostavku-dorogo",
    "khoteli-poluchit-bolshuiu-skidku-predlozhennaia-ne-ustroila", "dorogo",
    "khoteli-zakazat-prikhotlivoe-rastenie-no-peredumali-uznav-ob-ukhode",
    "khoteli-poluchit-neskolko-pozitsii-na-vybor-v-moment-dostavki-otkazatsia-ot-tekh-chto-ne-podoidut",
    "khoteli-predvaritelno-uvidet-foto-ot-sadovnika-rastenie-ne-iz-nalichiia",
    "oformili-zakaz-na-iskusstvennoe-rastenie-dumaia-chto-ono-zhivoe",
    "v-nalichii-net-nuzhnogo-iskusstvennogo-rasteniia", "slishkom-dolgo-otvechali", "tender", "cancel-other",
    "khoteli-predvaritelno-uvidet-iskusstvennye-rasteniia", "nevernaia-tsena-na-saite", "dubl-zakaza",
    "test", "tropik-doktor", "klient-v-chiornom-spiske", "sozdan-zakaz", "spam"
]


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


def _get_last_order(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Вспомогательная функция для получения данных о последнем заказе.
    ИСПРАВЛЕНО: Теперь использует поиск по ID клиента, что надежнее, чем прямой поиск заказа по телефону.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден. Невозможно получить данные о заказе.")
        return None

    normalized_phone = normalize_phone(phone_number)
    if not normalized_phone:
        return None

    # --- ШАГ 1: ПОЛУЧЕНИЕ ID КЛИЕНТА (наиболее надежный способ) ---
    customer_id = None
    customers_api_endpoint = f"{RETAILCRM_URL}/api/v5/customers"
    # Для поиска клиента по номеру телефона используем filter[name]
    customers_params = {
        "apiKey": RETAILCRM_API_KEY,
        "filter[name]": normalized_phone
    }

    try:
        customers_response = requests.get(customers_api_endpoint, params=customers_params, timeout=5)
        customers_response.raise_for_status()
        customers_data = customers_response.json()

        if customers_data.get('success') and customers_data.get('customers'):
            # Берем первого найденного клиента (Customer ID)
            customer_id = customers_data["customers"][0].get("id")

        if not customer_id:
            return None  # Клиент не найден

    except Exception:
        # При любой ошибке на шаге 1, считаем, что заказов нет.
        return None

    # --- ШАГ 2: ПОЛУЧЕНИЕ ЗАКАЗОВ ПО ID КЛИЕНТА ---
    orders_api_endpoint = f"{RETAILCRM_URL}/api/v5/orders"
    orders_params = {
        "apiKey": RETAILCRM_API_KEY,
        "filter[customerId]": customer_id,  # Ищем по ID клиента
    }

    try:
        response = requests.get(orders_api_endpoint, params=orders_params, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get('success') and data.get('orders'):
            # Сортируем заказы по дате создания в убывающем порядке, чтобы получить самый новый
            sorted_orders = sorted(data["orders"], key=lambda x: x.get("createdAt", ""), reverse=True)
            return sorted_orders[0]
        return None
    except Exception as e:
        # Не выводим ошибку при поиске, так как это может быть нормальным поведением
        return None


# --- НОВАЯ ФУНКЦИЯ ДЛЯ ПРОВЕРКИ НА ПОВТОРНЫЙ АНАЛИЗ (Добавлено) ---
def get_last_order_link_for_check(phone_number: str) -> Optional[str]:
    """
    Находит ID последнего заказа и формирует его прямую ссылку.
    Используется для проверки, был ли этот заказ уже проанализирован (т.е. есть ли он в Google Sheets).

    Args:
        phone_number: Номер телефона клиента.

    Returns:
        Прямая ссылка на последний заказ в RetailCRM или None, если заказ не найден.
    """
    last_order = _get_last_order(phone_number)

    if last_order and isinstance(last_order, dict):
        order_id = last_order.get('id')
        if order_id:
            # Формируем ссылку в том же виде, в котором она хранится в Google Sheets
            order_link = f"{RETAILCRM_URL}/orders/{order_id}/edit"
            return order_link

    return None
# -------------------------------------------------------------------


# --- НОВАЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ДЕТАЛЕЙ ЗАКАЗА ---
def _get_order_details_by_id(order_id: int) -> Optional[Dict[str, Any]]:
    """Получает полные детали заказа по его ID."""
    if not RETAILCRM_API_KEY:
        return None

    try:
        # Для получения полного состава заказа используем запрос /api/v5/orders/{externalId}
        # У нас есть id, поэтому используем его.
        url = f"{RETAILCRM_URL}/api/v5/orders/{order_id}?by=id&apiKey={RETAILCRM_API_KEY}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get('success') and data.get('order'):
            return data['order']
        return None
    except Exception as e:
        print(f"❌ Ошибка при получении деталей заказа {order_id}: {e}")
        return None


# --- НОВАЯ ОСНОВНАЯ ФУНКЦИЯ ДЛЯ АНАЛИЗА ДОКОМПЛЕКТА ---
def get_order_items_status(phone_number: str) -> Dict[str, bool]:
    """
    Проверяет состав последнего заказа клиента по номеру телефона
    на предмет наличия и растений, и кашпо.

    Возвращает словарь: {'has_plant': bool, 'has_cachepot': bool}
    Если заказа нет или произошла ошибка, возвращает {'has_plant': False, 'has_cachepot': False}.
    """
    items_status = {'has_plant': False, 'has_cachepot': False}

    last_order = _get_last_order(phone_number)
    if not last_order:
        return items_status

    order_id = last_order.get('id')
    if not order_id:
        return items_status

    order_details = _get_order_details_by_id(order_id)
    if not order_details or not order_details.get('items'):
        return items_status

    has_plant = False
    has_cachepot = False

    # Эвристика для определения типа товара
    for item in order_details['items']:
        item_name = item.get('offer', {}).get('name', '').lower()

        # 1. Поиск Кашпо
        if 'кашпо' in item_name or 'lechuza' in item_name or 'горшок' in item_name:
            has_cachepot = True

        # 2. Поиск Растений (игнорируем грунт, дренаж, пересадку, которые являются докомплектом)
        # Если это не кашпо/горшок, и не расходник, то считаем, что это растение
        if not has_cachepot and \
                'грунт' not in item_name and \
                'дренаж' not in item_name and \
                'пересадка' not in item_name and \
                'средство' not in item_name and \
                'ламп' not in item_name:  # Лампа - скорее допродажа, но исключим ее
            has_plant = True

        # Оптимизация: если уже найдены оба, можно прервать цикл
        if has_plant and has_cachepot:
            break

    return {'has_plant': has_plant, 'has_cachepot': has_cachepot}


def check_if_last_order_is_analyzable(phone_number: str) -> bool:
    """
    Проверяет, подлежит ли звонок клиента анализу на основе статуса ЕГО ПОСЛЕДНЕГО заказа.
    Звонок анализируется ТОЛЬКО, если:
    1. Заказ найден.
    2. Статус последнего заказа находится в списке ANALYZABLE_STATUS_CODES.

    Returns:
        True, если звонок подлежит анализу, иначе False.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден. Проверка статуса заказа невозможна. Возвращаем True.")
        return True # В случае ошибки API лучше анализировать, чтобы не пропустить

    last_order = _get_last_order(phone_number)

    if last_order:
        order_status = last_order.get("status")

        if order_status and order_status in ANALYZABLE_STATUS_CODES:
            print(f"✅ Статус для анализа: Последний заказ со статусом '{order_status}' (РАЗРЕШЕН).")
            return True
        elif order_status:
            print(f"❌ Статус для анализа: Последний заказ со статусом '{order_status}' (НЕ РАЗРЕШЕН).")
            return False
        else:
            print("❌ Статус для анализа: У последнего заказа отсутствует поле 'status'. Возвращаем False (поскольку нет четкого статуса).")
            return False # Если нет статуса, не анализируем
    else:
        # ИСПРАВЛЕНО: Клиенты без заказов теперь НЕ анализируются
        print(
            "❌ Статус для анализа: Заказы не найдены. Звонок НЕ анализируется (исключаем новых потенциальных клиентов).")
        return False # <--- ГЛАВНОЕ ИЗМЕНЕНИЕ: ВОЗВРАЩАЕМ FALSE


def check_if_phone_has_recent_order(phone_number: str, hours: int = 36) -> bool:
    """
    Проверяет, был ли у клиента заказ, оформленный в последние 'hours' часов.
    Args:
        phone_number: Номер телефона клиента.
        hours: Количество часов для проверки (по умолчанию 36).
    Returns:
        True, если найден хотя бы один недавний заказ, иначе False.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден. Проверка недавних заказов невозможна.")
        return False

    normalized_phone = normalize_phone(phone_number)
    if not normalized_phone:
        return False

    api_endpoint = f"{RETAILCRM_URL}/api/v5/orders"
    params = {
        "apiKey": RETAILCRM_API_KEY,
        "filter[customer]": normalized_phone,
    }

    print(f"🔍 Проверка недавних заказов: Ищем заказы для номера: {normalized_phone} за последние {hours} ч...")

    try:
        response = requests.get(api_endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("success") and data.get("orders"):
            now_utc = datetime.now(timezone.utc)
            time_cutoff = now_utc - timedelta(hours=hours)

            for order in data["orders"]:
                created_at_str = order.get("createdAt")
                if created_at_str:
                    created_at_dt = datetime.fromisoformat(created_at_str)
                    if created_at_dt.astimezone(timezone.utc) >= time_cutoff:
                        print(f"✅ Проверка недавних заказов: Найден заказ, созданный в {created_at_dt}. Соответствует.")
                        return True
            print("✅ Проверка недавних заказов: Заказы найдены, но ни один не создан за последние 36 часов.")
            return False
        else:
            print(f"ℹ️ Проверка недавних заказов: Заказы для номера {normalized_phone} не найдены.")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Проверка недавних заказов: Ошибка при поиске заказа: {e}")
        return False
    except Exception as e:
        print(f"❌ Проверка недавних заказов: Непредвиденная ошибка: {e}")
        return False


def get_order_link_by_phone(phone_number: str) -> str:
    """
    Ищет ID клиента по номеру телефона, а затем ID последнего заказа,
    чтобы сформировать прямую ссылку на заказ в RetailCRM.

    Args:
        phone_number: Номер телефона клиента.

    Returns:
        Прямая ссылка на последний заказ или ссылку на карточку клиента (запасной вариант)
        или пустая строка в случае ошибки.
    """
    if not RETAILCRM_API_KEY:
        print("❗ Ошибка: RETAILCRM_API_KEY не найден в .env. Невозможно подключиться к RetailCRM.")
        return ""

    normalized_input_phone = normalize_phone(phone_number)
    customer_id = None
    customer_card_link = ""  # Инициализируем ссылку на карточку клиента

    # --- Шаг 1: Ищем клиента по номеру телефона (используем filter[name]) ---
    customers_api_endpoint = f"{RETAILCRM_URL}/api/v5/customers"
    customers_params = {
        "apiKey": RETAILCRM_API_KEY,
        "filter[name]": normalized_input_phone  # Используем filter[name]
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
    last_order = _get_last_order(phone_number)
    manager_id = last_order.get("managerId") if last_order else None

    if not manager_id:
        print(f"ℹ️ CRM-поиск менеджера: Заказы или managerId не найдены для номера {normalize_phone(phone_number)}.")
        return None

    # --- Шаг 2: Получаем имя менеджера по managerId ---
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


if __name__ == "__main__":
    # Для целей тестирования замените на актуальные номера, которые есть в вашей CRM
    # В идеале: 1) Номер с заказом, где есть и растение, и кашпо. 2) Номер, где есть только растение. 3) Номер без заказов.
    test_phones = [
        "79165073740",  # Измените на номер с заказом в одном из анализируемых статусов (Тест 1)
        "79991234567"  # Измените на номер, у которого нет заказов (Тест 2)
    ]

    print("\n" + "=" * 50)
    print("=== ЗАПУСК ТЕСТИРОВАНИЯ RETAILCRM_INTEGRATION ===")
    print("=" * 50 + "\n")

    for i, phone in enumerate(test_phones):
        print(f"\n--- Тестирование для номера {phone} (Тест {i + 1}/{len(test_phones)}) ---")

        # 1. Проверка анализируемости
        print(">> 1. Проверка статуса для анализа (check_if_last_order_is_analyzable):")
        is_analyzable = check_if_last_order_is_analyzable(phone)
        print(f"   Результат: Подлежит ли звонок анализу: {is_analyzable}")

        # 2. Проверка состава заказа (НОВАЯ ФУНКЦИЯ)
        print(">> 2. Проверка состава последнего заказа (get_order_items_status):")
        items_status = get_order_items_status(phone)
        print(f"   Результат: {items_status}")

        # 3. Проверка ссылки на заказ
        print(">> 3. Проверка ссылки на заказ (get_order_link_by_phone):")
        link = get_order_link_by_phone(phone)
        print(f"   Результат: Ссылка: {link or 'Не найдена'}")

        # 4. Проверка менеджера
        print(">> 4. Проверка менеджера из CRM (get_manager_name_from_crm):")
        manager_name = get_manager_name_from_crm(phone)
        print(f"   Результат: Менеджер из CRM: {manager_name or 'Не найден'}")

        # 5. Проверка недавних заказов (для отладки)
        print(">> 5. Проверка недавних заказов (check_if_phone_has_recent_order):")
        has_recent_order = check_if_phone_has_recent_order(phone)
        print(f"   Результат: Есть ли недавний заказ: {has_recent_order}")

        print("\n" + "-" * 40)
