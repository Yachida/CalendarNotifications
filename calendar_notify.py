import os
from dotenv import load_dotenv
import requests
import datetime
import sys
from collections import defaultdict

load_dotenv()

NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
NOTION_DATABASE_ID = os.environ.get('NOTION_DATABASE_ID')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID')

NOTION_API_URL = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
NOTION_VERSION = "2022-06-28"

def get_today_events():
    today = datetime.date.today().isoformat()
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    filter_query = {
        "filter": {
            "property": "Date",
            "date": {
                "equals": today
            }
        }
    }
    response = requests.post(NOTION_API_URL, headers=headers, json=filter_query)
    response.raise_for_status()
    return response.json().get("results", [])

def get_next_week_events():
    today = datetime.date.today()
    # 翌週月曜～翌週日曜
    start_date = today + datetime.timedelta(days=(7 - today.weekday()))
    end_date = start_date + datetime.timedelta(days=6)
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    filter_query = {
        "filter": {
            "and": [
                {"property": "Date", "date": {"on_or_after": start_date.isoformat()}},
                {"property": "Date", "date": {"on_or_before": end_date.isoformat()}}
            ]
        }
    }
    response = requests.post(NOTION_API_URL, headers=headers, json=filter_query)
    response.raise_for_status()
    return response.json().get("results", [])

def format_event(event):
    props = event["properties"]
    title = props["Name"]["title"][0]["plain_text"] if props["Name"]["title"] and len(props["Name"]["title"]) > 0 else "(無題)"
    date_info = props["Date"]["date"] if "Date" in props and props["Date"]["date"] else None
    # Personプロパティのnameを取得（複数対応）
    person = ""
    if "Person" in props and props["Person"].get("people"):
        person = ", ".join([
            p.get("name", "")
            for p in props["Person"]["people"] if p.get("name")
        ])
    # 時間表示
    if date_info:
        start = date_info["start"]
        end = date_info.get("end")
        if "T" in start:
            start_time = start[11:16]
            end_time = end[11:16] if end else ""
            time_str = f"{start_time}-{end_time}" if end_time else start_time
            if person:
                main = f"{time_str} {person} {title}".strip()
            else:
                main = f"{time_str} {title}".strip()
        else:
            if person:
                main = f"{person} {title}".strip()
            else:
                main = f"{title}".strip()
    else:
        if person:
            main = f"{person} {title}".strip()
        else:
            main = f"{title}".strip()
    return f"- {main}"

def post_to_slack(message):
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN.strip()}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": SLACK_CHANNEL_ID.strip(),
        "text": message
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    res_json = response.json()
    if not res_json.get("ok"):
        raise Exception(f"Slack API error: {res_json}")

def main():
    mode = "daily"
    CALENDAR_DB_URL = os.environ.get("NOTION_CALENDAR_DB_URL", "")
    if not CALENDAR_DB_URL and NOTION_DATABASE_ID:
        dbid = NOTION_DATABASE_ID.replace("-", "")
        CALENDAR_DB_URL = f"https://www.notion.so/{dbid}"
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    if mode == "weekly":
        events = get_next_week_events()
        if not events:
            message = "No events scheduled for next week."
        else:
            day_events = defaultdict(list)
            for event in events:
                date_info = event["properties"]["Date"]["date"] if "Date" in event["properties"] and event["properties"]["Date"]["date"] else None
                day = date_info["start"][:10] if date_info else "(Unknown date)"
                day_events[day].append(event)
            lines = ["Next Week's Calendar Events"]
            weekday_en = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for day in sorted(day_events.keys()):
                dt = None
                try:
                    dt = datetime.datetime.strptime(day, "%Y-%m-%d")
                except Exception:
                    pass
                if dt:
                    weekday = weekday_en[dt.weekday()]
                    date_str = dt.strftime("%m/%d")
                    lines.append(f"■ {date_str} ({weekday})")
                else:
                    lines.append(f"■ {day}")
                for event in day_events[day]:
                    lines.append(format_event(event))
            if CALENDAR_DB_URL:
                lines.append(f"\nUpdate/Check Calendar DB: {CALENDAR_DB_URL}")
                lines.append("(Please add or edit events in Notion)")
            message = "\n".join(lines)
        post_to_slack(message)
        return
    # daily（平日朝）
    events = get_today_events()
    if not events:
        return  # イベントがなければ何も投稿しない
    else:
        lines = ["Today's Calendar Events"]
        for event in events:
            lines.append(format_event(event))
        if CALENDAR_DB_URL:
            lines.append(f"\nUpdate/Check Calendar DB: {CALENDAR_DB_URL}")
            lines.append("(Please add or edit events in Notion)")
        message = "\n".join(lines)
        post_to_slack(message)

def test_post_to_slack():
    """ダミーデータでSlack通知のみをテストする関数"""
    dummy_message = "【テスト通知】\n- 10:00-11:00 ダミーミーティング (担当: テストユーザー, 備考: テスト用送信)"
    post_to_slack(dummy_message)

def test_notion_connection():
    events = get_today_events()
    print(f"取得件数: {len(events)}")
    for event in events:
        print(event)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test_notion":
        test_notion_connection()
    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        test_post_to_slack()
    else:
        main()
