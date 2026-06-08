import os
import time
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SAKAI_URL = "https://sakai.ug.edu.gh/direct"
LOGIN_URL = f"{SAKAI_URL}/session.json"
ANNOUNCEMENTS_URL = f"{SAKAI_URL}/announcement/user.json"
ASSIGNMENTS_URL = f"{SAKAI_URL}/assignment/my.json"

TRACKING_FILE = "seen_notifications.json"

def load_seen():
    try:
        with open(TRACKING_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"announcements": [], "assignments": []}

def save_seen(seen_data):
    with open(TRACKING_FILE, "w") as f:
        json.dump(seen_data, f, indent=4)

def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram credentials missing")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Telegram notification sent!")
        else:
            print(f"Failed to send Telegram: {response.text}")
    except Exception as e:
        print(f"Error sending Telegram: {e}")

def run_once():
    username = os.getenv("SAKAI_USERNAME")
    password = os.getenv("SAKAI_PASSWORD")

    if not username or not password:
        print("Sakai credentials missing")
        return

    session = requests.Session()

    print("Logging in to Sakai...")
    try:
        login_resp = session.post(LOGIN_URL, data={"_username": username, "_password": password})
        if login_resp.status_code not in [200, 201]:
            print(f"Login failed: {login_resp.status_code}")
            return
    except Exception as e:
        print(f"Login error: {e}")
        return

    seen_data = load_seen()
    new_notifications = []

    # Announcements
    try:
        resp = session.get(ANNOUNCEMENTS_URL)
        if resp.status_code == 200:
            announcements = resp.json().get("announcement_collection", [])
            for ann in announcements:
                ann_id = ann.get("entityId")
                if ann_id not in seen_data["announcements"]:
                    msg = f"📢 *New Sakai Announcement*\n\n*Site:* {ann.get('siteTitle')}\n*Title:* {ann.get('title')}"
                    new_notifications.append(msg)
                    seen_data["announcements"].append(ann_id)
    except Exception as e: print(f"Announcements error: {e}")

    # Assignments
    try:
        resp = session.get(ASSIGNMENTS_URL)
        if resp.status_code == 200:
            assignments = resp.json().get("assignment_collection", [])
            for asn in assignments:
                asn_id = asn.get("entityId")
                if asn_id not in seen_data["assignments"]:
                    msg = f"📝 *New Sakai Assignment*\n\n*Title:* {asn.get('title')}\n*Due:* {asn.get('dueTime', {}).get('display', 'N/A')}"
                    new_notifications.append(msg)
                    seen_data["assignments"].append(asn_id)
    except Exception as e: print(f"Assignments error: {e}")

    if new_notifications:
        for msg in new_notifications:
            send_telegram(msg)
        save_seen(seen_data)
    else:
        print("No new updates.")

if __name__ == "__main__":
    run_once()
