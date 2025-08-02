import requests
import sys
import time


# הורדת קבצים מהאנטרנט, יש למלא את הקישור של האתר וגם את הרישור של ההורדה
def download_file(url, headers=None, filename='downloaded_file'):
    try:
        with requests.get(url, headers=headers, stream=True) as response:
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if 'text/html' in content_type:
                print('קיבלנו דף HTML במקום קובץ. כנראה בעיה בגישה לקובץ.')
                print(response.text[:1000])
                return

            total_length = response.headers.get('content-length')
            if total_length is None:
                print('לא ידוע גודל הקובץ מראש.')
                total_length = 0
            else:
                total_length = int(total_length)
                print(f'גודל הקובץ: {total_length / (1024*1024):.2f} MB')

            downloaded = 0
            chunk_size = 8192
            last_print_time = time.time()

            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # רק כל 10 שניות נעדכן את הפלט
                        if time.time() - last_print_time >= 10:
                            if total_length:
                                percent = downloaded / total_length * 100
                                print(f"הורדו: {downloaded // (1024*1024)}MB ({percent:.1f}%)")
                            else:
                                print(f"הורדו: {downloaded // (1024*1024)}MB")
                            last_print_time = time.time()

            print(f'\n✅ קובץ נשמר בשם: {filename}')

    except requests.exceptions.RequestException as e:
        print(f'❌ שגיאה בהורדה: {e}')


# דוגמה לשימוש:
# פה יש למלא את הקישור לקובץ ההורדה
url = 'https://www.emuparadise.me/roms/get-download.php?gid=155965&token=4c52e5ce232cd1967acb9a6a6c5aa448&mirror_available=true'
# פה יש למלא את הקישור לאתר
headers = {
    'Referer': 'https://www.emuparadise.me/PSP_ISOs/LEGO_Star_Wars_II_-_The_Original_Trilogy_(USA)/155965-download',
    'User-Agent': 'Mozilla/5.0'
}

filename = 'gime_download.rar'

download_file(url, headers, filename)
