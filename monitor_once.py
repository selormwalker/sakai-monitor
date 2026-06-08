import os
import time
import json
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SAKAI_URL = "https://sakai.ug.edu.gh/direct"
LOGIN_URL = f"{SAKAI_URL}/session.json"
ANNOUNCEMENTS_URL = f"{SAKAI_URL}/announcement/user.json"
ASSIGNMENTS_URL = f"{SAKAI_URL}/assignment/my.json"
SITES_URL = f"{SAKAI_URL}/site.json"

TRACKING_FILE = "seen_notifications.json"

def load_seen():
    try:
        with open(TRACKING_FILE, "r") as f:
            data = json.load(f)
            # Ensure new keys exist
            if "resources" not in data: data["resources"] = []
            if "last_summary_date" not in data: data["last_summary_date"] = ""
            return data
    except Exception:
        return {"announcements": [], "assignments": [], "resources": [], "last_summary_date": ""}

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
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Failed to send Telegram: {response.text}")
    except Exception as e:
        print(f"Error sending Telegram: {e}")

def get_site_link(site_id):
    return f"https://sakai.ug.edu.gh/portal/site/{site_id}"

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

    # 1. Check Announcements (Feature 4: Direct Links)
    try:
        resp = session.get(ANNOUNCEMENTS_URL)
        if resp.status_code == 200:
            announcements = resp.json().get("announcement_collection", [])
            for ann in announcements:
                ann_id = ann.get("entityId")
                if ann_id not in seen_data["announcements"]:
                    site_id = ann.get("siteId")
                    link = get_site_link(site_id)
                    msg = (f"📢 *New Announcement*\n\n"
                           f"*Site:* {ann.get('siteTitle')}\n"
                           f"*Title:* {ann.get('title')}\n\n"
                           f"🔗 [Open in Sakai]({link})")
                    new_notifications.append(msg)
                    seen_data["announcements"].append(ann_id)
    except Exception as e: print(f"Announcements error: {e}")

    # 2. Check Assignments (Feature 4: Direct Links)
    all_assignments = []
    try:
        resp = session.get(ASSIGNMENTS_URL)
        if resp.status_code == 200:
            all_assignments = resp.json().get("assignment_collection", [])
            for asn in all_assignments:
                asn_id = asn.get("entityId")
                if asn_id not in seen_data["assignments"]:
                    site_id = asn.get("context")
                    link = get_site_link(site_id)
                    due = asn.get("dueTime", {}).get("display", "N/A")
                    msg = (f"📝 *New Assignment*\n\n"
                           f"*Title:* {asn.get('title')}\n"
                           f"*Due:* {due}\n\n"
                           f"🔗 [Open in Sakai]({link})")
                    new_notifications.append(msg)
                    seen_data["assignments"].append(asn_id)
    except Exception as e: print(f"Assignments error: {e}")

    # 3. Check Resources (Feature 2)
    # This can be heavy, let's fetch for all sites the user is in
    try:
        sites_resp = session.get(SITES_URL)
        if sites_resp.status_code == 200:
            sites = sites_resp.json().get("site_collection", [])
            for site in sites:
                site_id = site.get("id")
                # Skip personal/special sites if needed
                if "~" in site_id: continue 
                
                res_url = f"{SAKAI_URL}/content/site/{site_id}.json"
                res_resp = session.get(res_url)
                if res_resp.status_code == 200:
                    content = res_resp.json().get("content_collection", [])
                    for item in content:
                        item_id = item.get("url") # Use URL as unique ID
                        if item_id and item_id not in seen_data["resources"]:
                            # Only notify about files, not folders
                            if not item_id.endswith("/"):
                                name = item.get("author") or "Lecturer"
                                title = item.get("title")
                                msg = (f"📁 *New Resource Uploaded*\n\n"
                                       f"*Site:* {site.get('title')}\n"
                                       f"*File:* {title}\n\n"
                                       f"🔗 [Download]({item_id})")
                                new_notifications.append(msg)
                            seen_data["resources"].append(item_id)
    except Exception as e: print(f"Resources error: {e}")

    # 4. Smart Deadline Summary (Feature 3)
    # Run once a day at 8:00 AM GMT (UG time)
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    
    if seen_data["last_summary_date"] != today_str and now.hour == 8:
        upcoming = []
        forty_eight_hours = now + timedelta(hours=48)
        
        for asn in all_assignments:
            due_millis = asn.get("dueTime", {}).get("time", 0)
            if due_millis:
                due_dt = datetime.fromtimestamp(due_millis / 1000.0, tz=timezone.utc)
                if now < due_dt <= forty_eight_hours:
                    upcoming.append(f"• *{asn.get('title')}*\n  Due: {asn.get('dueTime', {}).get('display')}")
        
        if upcoming:
            summary_msg = "☀️ *Morning Deadline Summary*\n\n" + "\n".join(upcoming) + "\n\nGood luck with your studies! 🚀"
            send_telegram(summary_msg)
        
        seen_data["last_summary_date"] = today_str

    # Send new notifications
    if new_notifications:
        for msg in new_notifications:
            send_telegram(msg)
        save_seen(seen_data)
    else:
        print("No new updates.")

if __name__ == "__main__":
    run_once()
