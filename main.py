import time
import datetime
import requests
import traceback

# ======== הגדרות ניתנות לשינוי ========

TOKEN = "0733582062:331781773"  # טוקן הגישה למערכת ימות
current_month = datetime.datetime.now().strftime("%Y-%m")
LOG_PATH = f"ivr2:/Log/LogFolderEnterExit-{current_month}.ymgr"  # הנתיב לקובץ הלוג הראשי
FOLDER_RANGE = [str(i) for i in range(1, 8)]  # שלוחות 7/1 עד 7/7
PARENT_FOLDER = "7"  # מספר השלוחה הראשית
BLOCK_LIMIT = 19  # כמה כניסות נדרשות לחסימה
CHECK_INTERVAL = 30  # זמן בין בדיקות (בשניות)
RUNTIME_MINUTES = 2  # זמן כולל שהסקריפט ירוץ
CHECK_BACK_HOURS = 0  # כמה שעות אחורה לבדוק
BLOCK_REDIRECT_FOLDER = "/7/100"  # שלוחה שאליה יועברו משתמשים במקרה חסימה
DEFAULT_PLAYFILE_TITLE = "יום בתהילים"  # קובץ מושמע כברירת מחדל לשלוחות פתוחות
SUMMARY_UPLOAD_PATH = "ivr2:/7/8/000.tts"  # הנתיב להעלאת סיכום הריצה

# ======== משתנים פנימיים ========

BLOCKED = set()  # שמירה אילו שלוחות נחסמו
BASE_URL = "https://www.call2all.co.il/ym/api"
SESSION_STATS = {f: set() for f in FOLDER_RANGE}  # רישום מלא של כניסות לפי שלוחה
ALL_LOGGED_ENTRIES = set()  # למניעת חישוב כפול
DAY_NAMES = {
    "1": "יום ראשון",
    "2": "יום שני",
    "3": "יום שלישי",
    "4": "יום רביעי",
    "5": "יום חמישי",
    "6": "יום שישי",
    "7": "שבת"
}


# ======== פונקציות ========

def hour_to_hebrew(hour):
    if hour == 0:
        return "שעה שתים עשרה בלילה"
    elif 1 <= hour <= 5:
        return f"שעה {hour} בלילה"
    elif 6 <= hour <= 11:
        return f"שעה {hour} בבוקר"
    elif hour == 12:
        return "שעה שתים עשרה בצהריים"
    elif 13 <= hour <= 17:
        return f"שעה {hour - 12} בצהריים"
    elif 18 <= hour <= 20:
        return f"שעה {hour - 12} בערב"
    else:
        return f"שעה {hour - 12} בלילה"

def now_str():
    now = datetime.datetime.now()
    hour_text = hour_to_hebrew(now.hour)
    minute = now.minute
    return f"{hour_text}, ו{minute} דקות."

def parse_datetime(date_str, time_str):
    try:
        return datetime.datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M:%S")
    except:
        return None

def download_file(path):
    url = f"{BASE_URL}/DownloadFile?token={TOKEN}&path={path}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    return None

def upload_file(path, content):
    url = f"{BASE_URL}/UploadFile"
    files = {'file': (path.split("/")[-1], content)}
    data = {'token': TOKEN, 'path': path}
    response = requests.post(url, data=data, files=files)
    if response.status_code == 200:
        print(f"✔ הועלה בהצלחה: {path}")
    else:
        print(f"✖ שגיאה בהעלאה ל: {path} – {response.status_code}")


def set_main_folder_lock(is_locked):
    path = f"ivr2:/{PARENT_FOLDER}/ext.ini"
    if is_locked:
        content = "type=menu\ntitle=חלוקת תהילים\nwhite_list=yes"
    else:
        content = "type=menu\ntitle=חלוקת תהילים"
    upload_file(path, content)

def reset_all_subfolders():
    print("🔁 מאפס את כל השלוחות לברירת מחדל...")
    for folder in FOLDER_RANGE:
        path = f"ivr2:/{PARENT_FOLDER}/{folder}/ext.ini"
        content = f"type=menu\ntitle={DEFAULT_PLAYFILE_TITLE}"
        upload_file(path, content)

def block_subfolder(folder):
    path = f"ivr2:/{PARENT_FOLDER}/{folder}/ext.ini"
    content = f"type=go_to_folder\ngo_to_folder={BLOCK_REDIRECT_FOLDER}"
    upload_file(path, content)
    BLOCKED.add(folder)

def analyze_log(text, start_dt):
    stats = {folder: [] for folder in FOLDER_RANGE}
    lines = text.splitlines()
    for line in lines:
        if not f"Folder#{PARENT_FOLDER}/" in line or "Phone#" not in line:
            continue

        parts = line.split("%")
        folder = phone = date = time_ = None
        folder_full_path = None
        dt = None

        for part in parts:
            if part.startswith("Phone#"):
                phone = part.split("#")[1]
            elif part.startswith("EnterDate#"):
                date = part.split("#")[1]
            elif part.startswith("EnterTime#"):
                time_ = part.split("#")[1]
            elif part.startswith(f"Folder#{PARENT_FOLDER}/"):
                folder_full_path = part.split("#")[1]  # לדוגמה: 7/1 או 7/1/9

        # נוודא שכל הנתונים קיימים
        if not (folder_full_path and phone and date and time_):
            continue

        dt = parse_datetime(date, time_)
        if not dt:
            continue

        parts_sub = folder_full_path.split("/")
        if len(parts_sub) >= 3 and parts_sub[2] == "9":
            parent_folder = parts_sub[1]
            if dt >= start_dt and parent_folder not in BLOCKED:
                print(f"🚨 זוהתה כניסה לשלוחה {PARENT_FOLDER}/{parent_folder}/9 אחרי תחילת הריצה – נחסמת מיידית")
                parent_path = f"ivr2:/{PARENT_FOLDER}/{parent_folder}/ext.ini"
                content = f"type=go_to_folder\ngo_to_folder={BLOCK_REDIRECT_FOLDER}"
                upload_file(parent_path, content)
                BLOCKED.add(parent_folder)

        elif len(parts_sub) >= 2:
            folder = parts_sub[1]

        # סופרים רק כניסות חדשות אחרי זמן ההתחלה
        if folder and folder in stats:
            unique_id = f"{folder}-{phone}-{date} {time_}"
            if dt >= start_dt and unique_id not in ALL_LOGGED_ENTRIES:
                stats[folder].append(unique_id)
                ALL_LOGGED_ENTRIES.add(unique_id)

    return stats

def create_summary_text(start_dt, end_dt, is_final):
    def dt_to_speech(dt):
        hour_text = hour_to_hebrew(dt.hour)
        minute = dt.minute
        return f"{hour_text}, ו{minute} דקות."
    summary = []
    if is_final:
        summary.append("המערכת סגורה כעת.")
    else:
        summary.append("המערכת פועלת כעת.")
    summary.append("סיכום הרצת הסקריפט.")
    summary.append(f"התחלה: {dt_to_speech(start_dt)}")
    summary.append(f"סיום: {dt_to_speech(end_dt)}")
    summary.append("")
    total_calls = 0
    blocked_days = []
    open_days = []
    for folder in FOLDER_RANGE:
        day_name = DAY_NAMES.get(folder, f"שלוחה {folder}")
        count = len(SESSION_STATS[folder])
        total_calls += count
        if folder in BLOCKED:
            blocked_days.append(f"{day_name} עם {count} כניסות")
        else:
            open_days.append(f"{day_name} עם {count} כניסות")
    summary.append(f"נחסמו: {len(blocked_days)} ימים. {', '.join(blocked_days)}.")
    summary.append(f"נשארו פתוחים: {len(open_days)} ימים. {', '.join(open_days)}.")
    summary.append(f"סה\"כ כניסות לכל הימים: {total_calls}.")
    return "\n".join(summary)

# ======== פונקציית הרצה ========

def main_loop():
    start_dt = datetime.datetime.now() - datetime.timedelta(hours=CHECK_BACK_HOURS)
    print(f"🟢 התחלה: {now_str()} | זמן ריצה: {RUNTIME_MINUTES} דקות\n")
    reset_all_subfolders()
    print("🔓 כל השלוחות אופסו בתחילת הריצה")

    set_main_folder_lock(False)
    try:
        while (datetime.datetime.now() - start_dt).total_seconds() < RUNTIME_MINUTES * 60:
            print("🔍 קריאת לוג ראשי...")
            text = download_file(LOG_PATH)
            if not text:
                print("⚠ לא ניתן לקרוא את קובץ הלוג הראשי. המתנה ובדיקה חוזרת.")
                time.sleep(CHECK_INTERVAL)
                continue
            stats = analyze_log(text, start_dt)
            total_checked = newly_blocked = still_open = 0
            for folder in FOLDER_RANGE:
                if folder in BLOCKED:
                    continue
                total_checked += 1
                new_entries = stats[folder]
                SESSION_STATS[folder].update(new_entries)
                count = len(new_entries)
                print(f"📞 {DAY_NAMES.get(folder, folder)}: {count} כניסות חדשות")
                if len(SESSION_STATS[folder]) > BLOCK_LIMIT:
                    print(f"🚫 חוסם את {DAY_NAMES.get(folder, folder)} (>{BLOCK_LIMIT})")
                    block_subfolder(folder)
                    newly_blocked += 1
                else:
                    still_open += 1
            # סיכום TTS לבדיקה זו
            end_dt = datetime.datetime.now()
            summary = create_summary_text(start_dt, end_dt, is_final=False)
            upload_file(SUMMARY_UPLOAD_PATH, summary)
            print(f"\n🔎 דוח ביניים: נבדקו {total_checked} | נחסמו {newly_blocked} | פתוחות: {still_open}")
            print("-" * 40 + "\n")
            time.sleep(CHECK_INTERVAL)
    except Exception as e:
        print("❗ שגיאה לא צפויה במהלך ההרצה:")
        print(traceback.format_exc())
    finally:
        reset_all_subfolders()
        end_dt = datetime.datetime.now()
        summary = create_summary_text(start_dt, end_dt, is_final=True)
        print("\n" + "=" * 50)
        print(summary)
        print("=" * 50 + "\n")
        upload_file(SUMMARY_UPLOAD_PATH, summary)
        print(f"📝 סיכום ההרצה נשמר והועלה אל: {SUMMARY_UPLOAD_PATH}")

        set_main_folder_lock(True)
        print("🔒 השלוחה הראשית ננעלה בסיום ההרצה.")


# ======== הפעלת התוכנית ========

if __name__ == "__main__":
    main_loop()
