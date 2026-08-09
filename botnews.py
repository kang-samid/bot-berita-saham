import feedparser
import requests
import time
import gspread
import json
import os
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import pytz

# Fitur Flask (Opsional: Try-Except agar tidak error jika dijalankan secara lokal)
try:
    from flask import Flask
    from threading import Thread
    app = Flask('')

    @app.route('/')
    def home():
        return "Bot News Saham Sedang Aktif"

    def run():
        app.run(host='0.0.0.0', port=8080)

    def start_flask():
        t = Thread(target=run)
        t.start()
except ImportError:
    def start_flask():
        pass

# --- 1. KONFIGURASI ---
BOT_TOKEN = '6467585568:AAH_vmQvGa7bBDI-lfmPhEzq2R_4SqcRs-s'
CHAT_ID = '@Kang_Zeyen'

# --- DAFTAR SAHAM TARGET (80 EMITEN) ---
TARGET_SAHAM = [
  "AADI", "ACES", "ADMR", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII",
  "BBCA", "BBNI", "BBRI", "BBTN", "BFIN", "BKSL", "BMRI", "BRMS", "BRPT", "BSDE",
  "BUKA", "BUMI", "CBDK", "CMRY", "CPIN", "CTRA", "CUAN", "DEWA", "DSNG", "ELSA",
  "EMTK", "ENRG", "ERAA", "ESSA", "EXCL", "GGRM", "GOTO", "HEAL", "HRTA", "HRUM",
  "ICBP", "INCO", "INDF", "INDY", "INKP", "ISAT", "ITMG", "JPFA", "JSMR", "KIJA",
  "KLBF", "KPIG", "LSIP", "MAPA", "MAPI", "MBMA", "MDKA", "MEDC", "MIKA", "MYOR",
  "NCKL", "PGAS", "PGEO", "PNLF", "PTBA", "PTRO", "PWON", "RAJA", "RATU", "SCMA",
  "SMGR", "SMRA", "SSIA", "TAPG", "TLKM", "TOWR", "TPIA", "UNTR", "UNVR", "WIFI"
]

# Ticker kata umum (membutuhkan validasi konteks ganda)
KATA_UMUM = {"RAJA", "RATU", "EMAS", "BUMI", "BUKA", "DEWA", "WIFI", "ELSA", "CUAN", "MIKA", "INDY"}

# Kata kunci judul yang menandakan berita RANGKUMAN / MULTI-EMITEN
KATA_RANGKUMAN = [
    "REKOMENDASI", "REKOMENDASIKAN", "IHSG", "TOP GAINERS", "TOP LOSERS", 
    "SOPING SAHAM", "KOLEKSI SAHAM", "PILAH-PILIH", "CERAH", "MERAH", 
    "KOMPAK", "POTENSI REBOUND", "CEK SAHAM", "DAFTAR SAHAM", "LAJU IHSG", "CUPON"
]

# --- 2. SETUP GOOGLE SHEETS ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

def init_google_sheets():
    try:
        creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("DatabaseBot").sheet1
    except Exception as e:
        print(f"Peringatan Google Sheets (Diabaikan jika lokal): {e}")
        return None

sheet = init_google_sheets()

def get_sent_links():
    if not sheet:
        return set()
    try:
        return set(sheet.col_values(1))
    except Exception as e:
        print(f"Error mengambil data dari Google Sheets: {e}")
        return set()

def save_to_sheet(link):
    if not sheet:
        return
    try:
        sheet.append_row([link])
    except Exception as e:
        print(f"Error menyimpan ke Google Sheets: {e}")

# --- 3. FUNGSI LOGIKA BOT ---
def generate_rss_urls(saham_list, chunk_size=20):
    urls = []
    for i in range(0, len(saham_list), chunk_size):
        chunk = saham_list[i:i + chunk_size]
        query_saham = "+OR+".join(chunk)
        url = f'https://news.google.com/rss/search?q={query_saham}&hl=id&gl=ID&ceid=ID:id'
        urls.append(url)
    return urls

def format_ke_wib(published_str):
    try:
        dt = parsedate_to_datetime(published_str)
        wib_tz = pytz.timezone('Asia/Jakarta')
        return dt.astimezone(wib_tz)
    except Exception:
        return None

def is_target_saham(title):
    title_upper = title.upper()

    # 1. Filter Kata Rangkuman / Multi-Emiten
    if any(kata in title_upper for kata in KATA_RANGKUMAN):
        return False, None

    # 2. Cek Emiten yang Cocok
    konteks_saham = ["SAHAM", "EMITEN", "TBK", "DIVIDEN", "IPO", "LAPORAN KEUANGAN","PENDAPATAN","LABA"]
    ada_konteks = any(k in title_upper for k in konteks_saham)
    
    matched_list = []
    for saham in TARGET_SAHAM:
        if re.search(rf'\b{saham}\b', title_upper):
            if saham in KATA_UMUM:
                if ada_konteks:
                    matched_list.append(saham)
            else:
                matched_list.append(saham)

    # 3. Abaikan jika berita menyebut lebih dari 1 emiten (Single emiten saja)
    if len(matched_list) == 1:
        return True, matched_list[0]
        
    return False, None

def send_telegram(title, link, source, pub_date_str, matched_saham):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    message_text = (
        f"📌 *[{matched_saham}]*\n"
        f"📢 *{title}*\n\n"
        f"📰 *Sumber:* {source}\n"
        f"⏰ *Waktu:* {pub_date_str}\n\n"
        f"👉 [Baca Selengkapnya Di Sini]({link})"
    )
    
    payload = {
        "chat_id": CHAT_ID,
        "text": message_text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(url, data=payload)
        return response.status_code == 200
    except Exception:
        return False

def check_and_send():
    rss_urls = generate_rss_urls(TARGET_SAHAM, chunk_size=20)
    wib_tz = pytz.timezone('Asia/Jakarta')
    now_wib = datetime.now(wib_tz)
    
    # Menghitung batas waktu sejak kemarin jam 00:00 WIB
    kemarin_12malam = (now_wib - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    sent_links = get_sent_links()
    collected_entries = []

    # STEP 1: Kumpulkan seluruh berita dari semua chunk RSS
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if entry.link in sent_links:
                continue
                
            raw_pub = entry.published if 'published' in entry else ''
            dt_wib = format_ke_wib(raw_pub)
            
            # Cek jika berita terbit sejak kemarin jam 00:00 WIB
            if dt_wib and dt_wib >= kemarin_12malam:
                is_match, matched_saham = is_target_saham(entry.title)
                
                if is_match:
                    source_name = entry.source.title if 'source' in entry else 'Google News'
                    pub_date_str = dt_wib.strftime("%d %b %Y, %H:%M WIB")
                    
                    collected_entries.append({
                        'title': entry.title,
                        'link': entry.link,
                        'source': source_name,
                        'pub_date_str': pub_date_str,
                        'matched_saham': matched_saham,
                        'dt_wib': dt_wib
                    })

    # STEP 2: Urutkan berita secara kronologis berdasarkan waktu (Terlama -> Terbaru)
    collected_entries.sort(key=lambda x: x['dt_wib'])

    # STEP 3: Kirim berita yang sudah diurutkan ke Telegram
    for item in collected_entries:
        if send_telegram(item['title'], item['link'], item['source'], item['pub_date_str'], item['matched_saham']):
            save_to_sheet(item['link'])
            sent_links.add(item['link'])
            time.sleep(1.5)

def main():
    print("Bot berjalan memantau berita saham...")
    while True:
        try:
            check_and_send()
        except Exception as e:
            print(f"Error loop utama: {e}")
        time.sleep(600)

# --- 4. EKSEKUSI ---
if __name__ == "__main__":
    start_flask()
    main()
