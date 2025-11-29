import os
import requests
import sys
import time
import subprocess
import tempfile
import shutil


# הקישור לאתר שממנו הגענו (Referer)
WEBSITE_URL = 'https://app.runwayml.com/video-tools/teams/a0548466646/ai-tools/generate?mode=tools&sessionId=8faa9943-76b8-41af-a358-64294642fa2a'


# הקישור לקובץ ההורדה
DOWNLOAD_URL = 'https://dnznrvs05pmza.cloudfront.net/4274bd38-5385-48c7-96a0-5a9858b0671c.mp4?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiNjU2M2U5MzRjODU3NmQ2MiIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc2NDU0NzIwMH0.CH5DubG8YxlhYXFcEZS-tid5RgcBFPY7OTc4cEK1pew&download=Gen-4+Turbo+%D7%90%D7%A0%D7%99+%D7%A8%D7%95%D7%A6%D7%94+%D7%A9%D7%AA%D7%99%D7%A7%D7%97+%D7%90%D7%AA+%D7%94%D7%AA%D7%9E%D7%95%D7%A0%D7%94+%D7%A9%D7%A0%D7%AA%D7%AA%D7%99+%D7%9C%D7%9A+%D7%A9%D7%A8%D7%95%D7%90%D7%99%D7%9D+%D7%91%D7%97%D7%95%D7%A8+%D7%A9%D7%A6%D7%95%D7%A0%D7%97+%D7%9E%D7%9E%D7%A1%D7%95%D7%A7+%D7%90%D7%A0%D7%99+%D7%A8%D7%95%D7%A6%D7%94+%D7%A9%D7%AA%D7%99%D7%A6%D7%95%D7%A8+%D7%A1%D7%A8%D7%98%D7%95%D7%9F+%D7%A9%D7%9E%D7%A8%D7%90%D7%94+%D7%90%D7%AA+%D7%94%D7%A9%D7%9C%D7%91%D7%99%D7%9D+%D7%90%D7%99%D7%9A+%D7%94%D7%91%D7%97%D7%95%D7%A8+%D7%A7%D7%95%D7%A4%D7%A5+%D7%9E%D7%94%D7%9E%D7%A1%D7%95%D7%A7+%D7%9C%D7%A7%D7%A8%D7%90%D7%AA+%D7%A6%D7%A0%D7%99%D7%97%D7%94+%D7%97%D7%95%D7%A4.mp4'


# הורדת קבצים מהאנטרנט, יש למלא את הקישור של האתר וגם את הרישור של ההורדה
def download_file(url, headers=None, filename='downloaded_file'):
    try:
        print(f'מתחיל הורדה מ: {url}')

        # הסרת referer אם הוא לא מתאים לדומיין
        if headers and 'Referer' in headers:
            from urllib.parse import urlparse
            referer_domain = urlparse(headers['Referer']).netloc
            target_domain = urlparse(url).netloc
            if referer_domain not in target_domain:
                print(f'הסרתי Referer לא תואם: {headers["Referer"]}')
                headers = headers.copy()
                del headers['Referer']

        with requests.get(url, headers=headers, stream=True, timeout=30) as response:
            response.raise_for_status()

            print(f'סטטוס תשובה: {response.status_code}')
            print(f'Content-Type: {response.headers.get("content-type")}')
            print(f'Content-Length: {response.headers.get("content-length")}')

            # קביעת סיומת לפי content-type
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                extension = '.pdf'
            elif 'zip' in content_type or 'rar' in content_type or 'octet-stream' in content_type:
                extension = '.rar'
            else:
                extension = '.bin'

            # עדכון שם הקובץ עם הסיומת המתאימה
            if '.' in filename:
                filename = filename.rsplit('.', 1)[0] + extension
            else:
                filename = filename + extension

            print(f'שומר כקובץ: {filename}')

            total_length = int(response.headers.get('content-length', 0))
            if total_length:
                print(f'גודל הקובץ: {total_length / (1024 * 1024):.2f} MB')
            else:
                print('גודל הקובץ לא זמין מה-headers')

            downloaded = 0
            chunk_size = 8192
            last_print_time = time.time()
            start_time = time.time()

            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # עדכון התקדמות כל 10 שניות
                        current_time = time.time()
                        if current_time - last_print_time >= 10:
                            elapsed = current_time - start_time
                            speed = downloaded / (1024 * 1024) / elapsed if elapsed > 0 else 0

                            if total_length:
                                percent = (downloaded / total_length) * 100
                                remaining = (total_length - downloaded) / (1024 * 1024) / speed if speed > 0 else 0
                                print(
                                    f"הורדה: {downloaded / (1024 * 1024):.1f}MB / {total_length / (1024 * 1024):.1f}MB ({percent:.1f}%) - מהירות: {speed:.1f}MB/s - זמן משוער: {remaining:.0f} שניות")
                            else:
                                print(f"הורדה: {downloaded / (1024 * 1024):.1f}MB - מהירות: {speed:.1f}MB/s")

                            last_print_time = current_time

            # בדיקת תקינות הקובץ
            file_size = os.path.getsize(filename)
            print(f'\n✅ הורדה הושלמה')
            print(f'גודל קובץ: {file_size / (1024 * 1024):.2f} MB')

            if total_length and file_size != total_length:
                print(f'אזהרה: גודל הקובץ שהורד ({file_size} בתים) שונה מהצפוי ({total_length} בתים)')

            # יצירת קובץ ZIP
            try:
                print('\nמכין קובץ ZIP...')
                zip_filename = 'gime_download.zip'
                
                # שימוש ב-zip ישירות על הקובץ
                if os.name == 'nt':  # Windows
                    # ב-Windows נשתמש ב-powershell
                    zip_cmd = f'Compress-Archive -Path "{filename}" -DestinationPath "{zip_filename}" -Force'
                    zip_cmd = ['powershell', '-Command', zip_cmd]
                else:  # Linux
                    # ב-Linux נשתמש ב-zip ישירות על הקובץ
                    zip_cmd = ['zip', '-j', zip_filename, filename]

                # הרצת פקודת הארכוב
                result = subprocess.run(zip_cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f'❌ שגיאה ביצירת קובץ ZIP:')
                    print(f'פלט שגיאה: {result.stderr}')
                    print(f'פלט סטנדרטי: {result.stdout}')
                    return False
                
                # בדיקה אם קובץ ה-ZIP נוצר בהצלחה
                if not os.path.exists(zip_filename):
                    print('❌ קובץ ה-ZIP לא נוצר בהצלחה')
                    return False
                
                # מחיקת הקובץ המקורי
                if os.path.exists(filename):
                    os.remove(filename)

                print(f'\n✅ קובץ ZIP נוצר: {zip_filename}')
                return True

            except Exception as e:
                print(f'❌ שגיאה בלתי צפויה ביצירת קובץ ZIP: {str(e)}')
                return False

    except requests.exceptions.RequestException as e:
        print(f'❌ שגיאה בהורדה: {e}')
        if 'filename' in locals() and os.path.exists(filename):
            try:
                os.remove(filename)
                print(f'הקובץ הפגום נמחק: {filename}')
            except Exception as e:
                print(f'שגיאה במחיקת הקובץ הפגום: {e}')
        return False

    except requests.exceptions.RequestException as e:
        print(f'❌ שגיאה בהורדה: {e}')


# דוגמה לשימוש:
# פה יש למלא את הקישור לקובץ ההורדה
url = DOWNLOAD_URL
# פה יש למלא את הקישור לאתר
headers = {
    'Referer': WEBSITE_URL,
    'User-Agent': 'Mozilla/5.0'
}

# שם הקובץ חייב להיות בדיוק gime_download.zip כי זה מה שה-GitHub Action מצפה לו
filename = 'gime_download.zip'

# הרצת הפונקציה להורדה
if download_file(url, headers, filename):
    print('ההורדה והמרה ל-RAR הסתיימו בהצלחה!')
else:
    print('אירעה שגיאה בתהליך ההורדה או ההמרה ל-RAR')
    sys.exit(1)  # יציאה עם קוד שגיאה
