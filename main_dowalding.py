import os
import requests
import sys
import time
import subprocess
import tempfile
import shutil
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import zipfile

# שינויים קטנים: imports לתמיכה ב-retries
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# הקישור לאתר שממנו הגענו (Referer)
WEBSITE_URL = 'https://apk.dog/download?file_id=2985964/fish-tycoon-2-virtual-aquarium'

# הקישור לקובץ ההורדה
DOWNLOAD_URL = 'https://apk.dog/go/?file_id=2985964&b=aHR0cHM6Ly8wNC5hcGsuZG9nL3N0b3JhZ2UvMTgvNjY5LzU0My82Njk1NDMvYXJtNjRfdjhhLWFybWVhYmlfdjdhLzI4NjdmZjFiNzc1YWJjNTQyMzM4NTI4YmNkMGU3YTYzL0Zpc2hfVHljb29uXzItMS4xMC4xNzEuYXBrP3M9NHY3djBqaUlMMmduMGYxeDMzb0NpdyZlPTE3NjA3NDE5MDkmbGFuZz1lbiZhcGtfaWQ9NTAwNjMwJnByZW1pdW1fc3BlZWQ9MA=='


# --- פונקציות עזר חדשות/מעודכנות ---

def create_session_with_retries(headers=None):
    """
    יוצר requests.Session עם headers ו-retries כדי לשמר עוגיות ולמנוע חסימות זמניות.
    """
    sess = requests.Session()
    if headers:
        sess.headers.update(headers)
    retries = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    adapter = HTTPAdapter(max_retries=retries)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    return sess


def find_apkpure_direct_link(download_page_url, session):
    """
    מקבל URL של עמוד ההורדה (apkpure /download) ומחזיר את הקישור הישיר ל-d.apkpure.com
    """
    print(f'מגרד את עמוד ההורדה כדי למצוא קישור ישיר: {download_page_url}')
    r = session.get(download_page_url, timeout=30)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, 'html.parser')

    # חפש href שמכיל d.apkpure.com (הקישור הישיר ל־APK/XAPK)
    for tag in soup.find_all(href=True):
        href = tag['href']
        if 'd.apkpure.com' in href:
            real = urljoin(download_page_url, href)
            print('נמצא קישור ישיר להורדה:', real)
            return real

    # אפשרות נוספת: חפש לינקים עם טקסט "Click here" או כפתור הורדה
    click_here = soup.find('a', string=re.compile(r'Click here|Click here to download|Download APK|Download XAPK', re.I))
    if click_here and click_here.has_attr('href'):
        real = urljoin(download_page_url, click_here['href'])
        print('נמצא קישור בעזרת טקסט "Click here":', real)
        return real

    # ניסיון למצוא בקוד JS/meta - חיפוש גנרי בכל הטקסט
    m = re.search(r'https?://d\.apkpure\.com[^\s\'"]+', html)
    if m:
        real = m.group(0)
        print('נמצא קישור ישיר בתוך ה-HTML/JS:', real)
        return real

    raise Exception('לא נמצא קישור ישיר ל-d.apkpure.com בעמוד ההורדה')


# הורדת קבצים מהאנטרנט, יש למלא את הקישור של האתר וגם את הרישור של ההורדה
def download_file(url, headers=None, filename='downloaded_file', session=None):
    """
    הורדה כללית:
    - אם ה-URL מחזיר content-type של HTML או נראה כמו דף (אין סיומת קובץ),
      נוריד את הדף + משאבים (CSS/JS/Images) לתיקיה זמנית וארכיב אותה כ-ZIP.
    - אחרת, יוריד קובץ רגיל ויעשה ZIP של הקובץ.
    החבילה הסופית תמיד תשמר בשם ZIP (filename אם מסתיים ב-.zip).
    """

    # קבע שם קובץ ZIP סופי (GitHub Action מצפה ל'gime_download.zip')
    zip_filename = filename if filename.lower().endswith('.zip') else 'gime_download.zip'

    # וודא שיש session אם עדיף
    sess = session if session is not None else create_session_with_retries(headers=headers)

    try:
        print(f'מתחיל הורדה מ: {url}')

        # הסרת Referer אם לא מתאים
        if headers and 'Referer' in headers:
            referer_domain = urlparse(headers['Referer']).netloc
            target_domain = urlparse(url).netloc
            if referer_domain not in target_domain:
                print(f'הסרתי Referer לא תואם: {headers["Referer"]}')
                headers = headers.copy()
                del headers['Referer']
                # אם session קיים - עדכן גם שם
                if sess:
                    sess.headers.pop('Referer', None)

        # ראשוני: בקשת HEAD לנסות לברר Content-Type (חסין לשרתים שלא תומכים)
        try:
            head = sess.head(url, allow_redirects=True, timeout=15)
            content_type = head.headers.get('content-type', '').lower()
        except Exception:
            content_type = ''

        # תנאים להתייחס כ"דף אינטרנט":
        url_path = urlparse(url).path
        looks_like_file = '.' in url_path.split('/')[-1]  # אם יש סיומת בנתיב
        treat_as_webpage = ('text/html' in content_type) or (not looks_like_file)

        if treat_as_webpage:
            print('זוהה דף אינטרנט — יוריד דף ומשאבים לצפייה לא מקוונת.')

            # צור תיקיה זמנית לשמירת דף ומשאביו
            tmpdir = tempfile.mkdtemp(prefix='page_dl_')
            assets_dir = os.path.join(tmpdir, 'assets')
            os.makedirs(assets_dir, exist_ok=True)

            # ניסיון להשתמש ב-wget אם קיים (הכי אמין לשימור דפים מורכבים)
            wget_path = shutil.which('wget')
            if wget_path:
                print('נמצא wget במערכת — משתמש בו להורדת הדף ושימור כל המשאבים.')
                # פקודת wget: הורדה של הדף + כל המשאבים, המרת קישורים לפתיחה לא מקוונת
                wget_cmd = [
                    wget_path,
                    '--page-requisites',       # הורדת CSS/JS/Images
                    '--convert-links',         # המרת קישורים ליחסי מקומי
                    '--adjust-extension',      # הוספת .html לפי צורך
                    '--span-hosts',            # הורדת משאבים הממוקמים בדומיינים חיצוניים
                    '--no-parent',
                    '--directory-prefix', tmpdir,
                    url
                ]
                result = subprocess.run(wget_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print('וואטש: wget החזיר שגיאה, מאפס ל-fallback של Python.')
                    print('stdout:', result.stdout)
                    print('stderr:', result.stderr)
                    # נמשיך ל-fallback של Python
                else:
                    # ארוז את כל התיקייה שנוצרה ב־ZIP
                    with zipfile.ZipFile(zip_filename, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                        for root, dirs, files in os.walk(tmpdir):
                            for f in files:
                                full = os.path.join(root, f)
                                rel = os.path.relpath(full, tmpdir)
                                zf.write(full, arcname=rel)
                    print(f'\n✅ קובץ ZIP נוצר: {zip_filename}')
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    return True

            # אם אין wget או הוא נכשל — נבצע fallback מבוסס BeautifulSoup (פשוט אך עובד טוב לרוב הדפים)
            print('מבצע fallback: הורדת HTML ו־משאבים באמצעות Python + BeautifulSoup.')

            resp = sess.get(url, timeout=30)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            # אסוף רשימת משאבים להורדה
            resource_tags = [
                ('img', 'src'),
                ('script', 'src'),
                ('link', 'href'),  # בדרך כלל CSS (rel=stylesheet)
            ]

            downloaded_map = {}  # מיפוי URL -> local filename

            def save_resource(res_url):
                # חיבור ל-URL מוחלט
                abs_url = urljoin(url, res_url)
                if abs_url in downloaded_map:
                    return downloaded_map[abs_url]
                try:
                    r = sess.get(abs_url, stream=True, timeout=20)
                    r.raise_for_status()
                    # שם הקובץ שמור: ננסה לשמור את שם הבסיס של הנתיב, אם חסר - נייצר שם
                    path = urlparse(abs_url).path
                    basename = os.path.basename(path) or 'resource'
                    # הימנע מקונפליקטים בשם
                    dest_name = basename
                    i = 1
                    while os.path.exists(os.path.join(assets_dir, dest_name)):
                        dest_name = f'{i}_{basename}'
                        i += 1
                    dest_path = os.path.join(assets_dir, dest_name)
                    with open(dest_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    downloaded_map[abs_url] = os.path.join('assets', dest_name)  # יחסית ל־tmpdir
                    return downloaded_map[abs_url]
                except Exception as e:
                    # לא הצלחנו להוריד את המשאב — נמשיך בלי להעתיקו
                    return None

            # עבור כל תג רלוונטי — הורד את המשאב והחלף הקישורים ליחסי
            for tag, attr in resource_tags:
                for node in soup.find_all(tag):
                    if not node.has_attr(attr):
                        continue
                    # התעלם מקישורים data: או javascript:void(0)
                    val = node[attr]
                    if not val or val.strip().startswith('data:') or val.strip().startswith('javascript:'):
                        continue
                    local = save_resource(val)
                    if local:
                        node[attr] = local  # יחסית ל־tmpdir

            # שמור את ה-HTML שהותאם
            index_path = os.path.join(tmpdir, 'index.html')
            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(str(soup))

            # ארוז את התיקיה כ-ZIP
            with zipfile.ZipFile(zip_filename, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(tmpdir):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, tmpdir)
                        zf.write(full, arcname=rel)

            print(f'\n✅ קובץ ZIP נוצר: {zip_filename}')
            shutil.rmtree(tmpdir, ignore_errors=True)
            return True

        else:
            # טיפול בקבצים רגילים — מבוסס על הקוד הקיים (stream)
            with sess.get(url, stream=True, timeout=30) as response:
                response.raise_for_status()

                print(f'סטטוס תשובה: {response.status_code}')
                print(f'Content-Type: {response.headers.get("content-type")}')
                print(f'Content-Length: {response.headers.get("content-length")}')

                content_type = response.headers.get('content-type', '').lower()
                # נחלץ סיומת סבירה
                if 'pdf' in content_type:
                    extension = '.pdf'
                elif 'zip' in content_type or 'rar' in content_type or 'octet-stream' in content_type:
                    extension = '.rar'
                else:
                    extension = os.path.splitext(urlparse(url).path)[1] or '.bin'

                # קבצים יורדים לשם מקומי זמני קודם
                tmp_file = tempfile.NamedTemporaryFile(delete=False)
                tmp_file.close()
                download_filename = tmp_file.name + extension

                print(f'שומר כקובץ: {download_filename}')

                total_length = int(response.headers.get('content-length', 0) or 0)
                downloaded = 0
                chunk_size = 8192
                last_print_time = time.time()
                start_time = time.time()

                with open(download_filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

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

                file_size = os.path.getsize(download_filename)
                print(f'\n✅ הורדה הושלמה — גודל קובץ: {file_size / (1024 * 1024):.2f} MB')

                # צרף את הקובץ ל-ZIP בשם zip_filename
                with zipfile.ZipFile(zip_filename, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.write(download_filename, arcname=os.path.basename(download_filename))

                # מחק את הקובץ המקורי
                try:
                    os.remove(download_filename)
                except Exception:
                    pass

                print(f'\n✅ קובץ ZIP נוצר: {zip_filename}')
                return True

    except requests.exceptions.RequestException as e:
        print(f'❌ שגיאה בהורדה: {e}')
        return False
    except Exception as e:
        print(f'❌ שגיאה בלתי צפויה: {e}')
        return False


# דוגמה לשימוש (חלק זה לא מחקתי — רק עדכנתי לקרוא ל-find_apkpure_direct_link לפני ההורדה):
url = DOWNLOAD_URL
# פה יש למלא את הקישור לאתר
headers = {
    'Referer': WEBSITE_URL,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

# שם הקובץ חייב להיות בדיוק gime_download.zip כי זה מה שה-GitHub Action מצפה לו
filename = 'gime_download.zip'

# צור session שישמש לכל הבקשות
session = create_session_with_retries(headers=headers)

# השינוי: קודם נסרוק את העמוד כדי למצוא את ה-link הישיר (d.apkpure.com)
try:
    real_download_url = find_apkpure_direct_link(DOWNLOAD_URL, session)
except Exception as e:
    print('לא הצלחתי למצוא קישור ישיר בעמוד ההורדה:', e)
    print('נסה להריץ מקומית או לבדוק אם ה-IP של ה-runner חסום.')
    sys.exit(1)

# הרצת הפונקציה להורדה (כעת מעבירים את ה-session)
if download_file(real_download_url, headers, filename, session=session):
    print('ההורדה והמרה ל-ZIP הסתיימו בהצלחה!')
else:
    print('אירעה שגיאה בתהליך ההורדה או ההמרה ל-ZIP')
    sys.exit(1)  # יציאה עם קוד שגיאה
