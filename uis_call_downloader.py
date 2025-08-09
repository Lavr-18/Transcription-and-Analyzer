import requests
import os
import json
import time  # Import time for delays
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from retailcrm_integration import get_order_link_by_phone  # Import function for RetailCRM
from pathlib import Path
import re # Import re for get_next_call_index

# Load token from .env
load_dotenv()
ACCESS_TOKEN = os.getenv("UIS_API_TOKEN")

# Define Moscow timezone (UTC+3)
MSK = timezone(timedelta(hours=3))


def get_calls_report(date_from, date_to):
    """
    Retrieves call report from UIS server for a specified period.
    Includes retry logic for increased resilience to network errors.
    """
    url = 'https://dataapi.uiscom.ru/v2.0'
    payload = {
        "id": "id777",
        "jsonrpc": "2.0",
        "method": "get.calls_report",
        "params": {
            "access_token": ACCESS_TOKEN,
            "date_from": date_from,
            "date_till": date_to
        }
    }

    print(f"🔍 Getting calls from {date_from} to {date_to}...")

    max_retries = 5  # Maximum number of attempts
    retry_delay = 1  # Initial delay in seconds (will double)

    for attempt in range(max_retries):
        try:
            # Timeout set: 10 sec for connection, 60 sec for read
            response = requests.post(url, json=payload, timeout=(10, 60))
            response.raise_for_status()  # Raises an exception for HTTP errors (4xx or 5xx)
            result = response.json()

            calls = result.get("result", {}).get("data", [])
            if not isinstance(calls, list):
                raise ValueError("Invalid data format: 'result.data' must be a list of calls")

            print(f"✅ Calls received: {len(calls)}")
            return calls
        except (requests.exceptions.RequestException, ValueError) as e:
            # Catch network errors, timeouts, and data format errors
            if attempt < max_retries - 1:
                print(
                    f"⚠️ Error getting calls (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {retry_delay} sec...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"❌ Error getting calls after {max_retries} attempts: {e}")
                return []  # Return empty list after failed attempts
        except Exception as e:
            # Catch any other unexpected errors
            print(f"❌ Unexpected error in get_calls_report: {e}")
            return []


def get_next_call_index(directory):
    """
    Determines the next available index for a new callN.mp3 file,
    to avoid overwriting and continue numbering.
    Searches for files matching the pattern 'call{index}_{phone_number}.mp3'.
    """
    existing_files = list(Path(directory).glob("call*.mp3"))
    used_indexes = set()
    for f in existing_files:
        try:
            # Extract number from filename (e.g., "call123_79001234567.mp3" -> 123)
            # Regular expression modified to correctly account for phone number in filename
            match = re.match(r'call(\d+)(?:_\d+)?\.mp3', f.name)
            if match:
                number = int(match.group(1))
                used_indexes.add(number)
        except ValueError:
            # Ignore files whose names do not match the pattern
            continue
    # Return max used index + 1, or 1 if no files exist
    return max(used_indexes, default=0) + 1

def _get_call_duration(call: dict) -> int | None:
    """Helper function to robustly get call duration."""
    duration = call.get("total_duration") # Try to get directly
    if duration is None:
        duration = call.get("raw", {}).get("total_duration") # Fallback to 'raw'
    return duration


def download_record(call, index, target_dir) -> Path | None:
    """
    Downloads a specific call recording, saves related information,
    and searches for an order link in RetailCRM.
    The filename will be in the format call{index}_{phone_number}.mp3.
    Returns the path to the created call_info.json file if created, otherwise None.
    """
    talk_id = call.get("communication_id")
    records = call.get("call_records", [])
    total_duration = _get_call_duration(call) # Use the helper function

    # Skip if no talk ID, no records, or duration is too short
    if not talk_id or not records or total_duration is None or total_duration < 20:
        print(f"Warning: Skipping call {call.get('communication_id', 'N/A')} due to missing info or duration < 20s. Duration: {total_duration}s")
        return None  # Return None, as info file will not be created

    record_hash = records[0]  # Take the hash of the first call record
    # NEW: Form the full link to the call recording
    record_url = f"https://app.uiscom.ru/system/media/talk/{talk_id}/{record_hash}/"

    # Phone number can be at the top level or inside "raw"
    contact_phone = call.get("contact_phone_number") or call.get("raw", {}).get("contact_phone_number", "")

    # Include phone number in filename for consistent identification
    base_filename = f"call{index}"
    if contact_phone:
        base_filename += f"_{contact_phone}"

    filename = Path(target_dir) / f"{base_filename}.mp3"
    info_filename = Path(target_dir) / f"{base_filename}_call_info.json"


    if filename.exists():
        print(f"⏭ Recording {filename.name} already exists, skipping.")
    else:
        print(f"⬇ Downloading {filename.name}...")
        try:
            # Timeout set: 10 sec for connection, 30 sec for read
            response = requests.get(record_url, timeout=(10, 30)) # Use record_url
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"✅ Saved: {filename.name}")
            else:
                print(f"⚠ Download error {record_url}: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Network request error while downloading {talk_id}: {e}")
        except Exception as e:
            print(f"❌ Unknown error while downloading {talk_id}: {e}")

    order_link = ""
    if contact_phone:
        order_link = get_order_link_by_phone(contact_phone)

    try:
        call_info = {
            "start_time": call.get("start_time", ""),
            "raw": call,
            "customer_card_link": order_link,
            "contact_phone_number": contact_phone,
            "record_link": record_url # NEW: Add call recording link
        }
        with open(info_filename, 'w', encoding='utf-8') as f:
            json.dump(call_info, f, indent=2, ensure_ascii=False)
        print(f"📝 Information saved: {info_filename.name}")
        return info_filename  # Return path to the created file
    except Exception as e:
        print(f"❌ Error saving call_info for {talk_id}: {e}")
        return None  # Return None in case of save error


def download_calls(start_time: datetime, end_time: datetime) -> list[Path]:
    """
    Main function for downloading calls within a specified period.
    Returns a list of paths to created call_info.json files.
    """
    print("🚀 Starting call download")

    if not ACCESS_TOKEN:
        print("❗ ACCESS_TOKEN not found in .env. Make sure .env file exists and contains ACCESS_TOKEN.")
        return []

    date_from_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    date_to_str = end_time.strftime("%Y-%m-%d %H:%M:%S")

    folder_date = end_time.strftime("%d.%m.%Y")
    target_dir = Path("audio") / f"звонки_{folder_date}"
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Checking or creating call folder: {target_dir}")

    downloaded_call_info_paths = []

    try:
        calls = get_calls_report(date_from_str, date_to_str)
        if not calls:
            print("ℹ️ No calls for the specified period.")
            return []

        current_idx = get_next_call_index(str(target_dir))
        for call in calls:
            # Filter calls by duration (longer than 20 seconds)
            total_duration = _get_call_duration(call) # Use the helper function
            if total_duration is None or total_duration < 20:
                print(f"⏩ Skipping call {call.get('communication_id', 'N/A')} due to short duration: {total_duration}s")
                continue # Skip to the next call

            # Only add path if download_record successfully created the file
            info_file_path = download_record(call, current_idx, target_dir)
            if info_file_path:
                downloaded_call_info_paths.append(info_file_path)
            current_idx += 1

    except Exception as e:
        print(f"❗ Error executing call download script: {e}")

    return downloaded_call_info_paths


if __name__ == "__main__":
    # Example usage for testing the module separately
    today = datetime.now(MSK)
    test_start_time = today.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    test_end_time = today.replace(hour=23, minute=59, second=59, microsecond=999999) - timedelta(days=1)

    print(
        f"\n--- Testing download_calls for period: {test_start_time.strftime('%Y-%m-%d %H:%M:%S')} - {test_end_time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    download_calls(test_start_time, test_end_time)
    print("\nCall download completed.")