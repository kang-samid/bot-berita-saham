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
from flask import Flask
from threading import Thread
from google.oauth2.service_account import Credentials

# --- 1. KONFIGURASI BOT TELEGRAM ---
BOT_TOKEN = '6467585568:AAH_vmQvGa7bBDI-lfmPhEzq2R_4SqcRs-s'
CHAT_ID = '@Kang_Zeyen'

# --- DAFTAR SAHAM TARGET (80 EMITEN) ---
TARGET_SAHAM = [
  "AADI", "ACES", "ADMR", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII",
  "BBCA", "BBNI", "BBRI", "BBTN", "BFIN", "BKSL", "BMRI", "BRMS", "BRPT", "BSDE",
  "BUMI", "CBDK", "CMRY", "CPIN", "CTRA", "CUAN", "DEWA", "DSNG", "ELSA", "EMTK", 
  "ENRG", "ERAA", "ESSA", "EXCL", "GGRM", "GOTO", "HEAL", "HRTA", "HRUM", "ICBP", 
  "INCO", "INDF", "INDY", "INKP", "ISAT", "ITMG", "JPFA", "JSMR", "KIJA", "KLBF", 
  "KPIG", "LSIP", "MAPA", "MAPI", "MBMA", "MDKA", "MEDC", "MIKA", "MYOR", "NCKL", 
  "PGAS", "PGEO", "PNLF", "PTBA", "PTRO", "PWON", "RAJA", "RATU", "SCMA", "SMGR", 
  "SMRA", "SSIA", "TAPG", "TLKM", "TOWR", "TPIA", "UNTR", "UNVR", "WIFI"
]

# Ticker kata umum biasa
KATA_UMUM = {"RAJA", "RATU", "EMAS", "BUMI", "BUKA", "DEWA", "WIFI", "ELSA", "CUAN", "MIKA", "INDY"}

# Kata kunci penyaring RANGKUMAN / MULTI-EMITEN
KATA_RANGKUMAN = [
    "REKOMENDASI", "REKOMENDASIKAN", "IHSG", "TOP GAINERS", "TOP LOSERS", 
    "SOPING SAHAM", "KOLEKSI SAHAM", "PILAH-PILIH", "CERAH", "MERAH", 
    "KOMPAK", "POTENSI REBOUND", "CEK SAHAM", "DAFTAR SAHAM", "LAJU IHSG", "CUPON"
]

# --- DICTIONARY PENYARING KHUSUS ---
SPECIAL_FILTERS = {
    "ANTM": {
        "forbidden": [
            "HARGA EMAS", "LOGAM MULIA", "EMAS ANTAM", "HARGA JUAL EMAS", 
            "EMAS DUNIA", "XAUUSD", "BUYBACK EMAS", "PERAK ANTAM", 
            "HARGA PERAK", "PERAK HARI INI"
        ],
        "required": [
            "SAHAM", "EMITEN", "TBK", "KINERJA", "LABA", "DIVIDEN", 
            "IPO", "LAPORAN KEUANGAN", "PROSPEK", "PENDAPATAN", "OPERASIONAL", "TAMBANG"
        ]
    }
}

# --- 2. SETUP FLASK SERVER (RENDER KEEP-ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot News Saham Aktif di Render!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 3. SETUP GOOGLE SHEETS ---
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def init_sheet():
    try:
        creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("DatabaseBot").sheet1
    except Exception as e:
        print(f"Error Koneksi Google Sheets: {e}")
        return None

sheet = init_sheet()

def get_sent_history():
    """Mengambil link (Kolom A) dan judul bersih (Kolom B) dari Google Sheets"""
    if not sheet:
        return set(), set()
    try:
        all_rows = sheet.get_all_values()
        sent_links = set(row[0] for row in all_rows if len(row) >= 1)
        sent_titles = set(row[1] for row in all_rows if len(row) >= 2)
        return sent_links, sent_titles
    except Exception as e:
        print(f"Error mengambil data sheet: {e}")
        return set(), set()

def save_to_sheet(link, cleaned_title):
    """Menyimpan link di Kolom A dan Cleaned Title di Kolom B"""
    if not sheet:
        return
    try:
        sheet.append_row([link, cleaned_title])
    except Exception as e:
        print(f"Error menyimpan ke sheet: {e}")

# --- 4. FUNGSI LOGIKA BOT ---
def clean_title(title):
    """Normalisasi judul secara mendalam (menghapus nama media & karakter khusus)"""
    title_main = re.split(r'[-|]', title)[0]  # Potong nama media di akhir judul
    return re.sub(r'[^a-zA-Z0-9]', '', title_main).lower()

def generate_rss_urls(saham_list, chunk_size=15):
    """Membagi query menjadi grup berformat Google Search resmi"""
    urls = []
    for i in range(0, len(saham_list), chunk_size):
        chunk = saham_list[i:i + chunk_size]
        query_saham = "%20OR%20".join(chunk)
        urls.append(f'https://news.google.com/rss/search?q=({query_saham})&hl=id&gl=ID&ceid=ID:id')
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

    # 1. Filter Kata Rangkuman / Multi-Emiten Umum
    if any(kata in title_upper for kata in KATA_RANGKUMAN):
        return False, None

    matched_list = []
    konteks_generik = ["SAHAM", "EMITEN", "TBK", "DIVIDEN", "IPO", "LAPORAN KEUANGAN","PENDAPATAN","LABA"]

    # 2. Iterasi Pencocokan Emiten
    for saham in TARGET_SAHAM:
        if re.search(rf'\b{saham}\b', title_upper):
            
            # Pengecekan Aturan Khusus jika ada di Dictionary (Misal: ANTM)
            if saham in SPECIAL_FILTERS:
                rule = SPECIAL_FILTERS[saham]
                if any(bad in title_upper for bad in rule["forbidden"]):
                    if not any(good in title_upper for good in rule["required"]):
                        continue  # Abaikan berita komoditas emas/perak fisik
            
            # Pengecekan KATA_UMUM biasa
            elif saham in KATA_UMUM:
                if not any(k in title_upper for k in konteks_generik):
                    continue

            matched_list.append(saham)

    # 3. Hanya loloskan jika persis 1 emiten yang cocok
    return (True, matched_list[0]) if len(matched_list) == 1 else (False, None)

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
    rss_urls = generate_rss_urls(TARGET_SAHAM, chunk_size=15)
    wib_tz = pytz.timezone('Asia/Jakarta')
    now_wib = datetime.now(wib_tz)
    
    # Batas waktu: Sejak kemarin jam 00:00 WIB
    kemarin_12malam = (now_wib - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Ambil riwayat terkirim (Link & Cleaned Title) dari Google Sheets
    sent_links, sent_titles = get_sent_history()
    collected_entries = []

    # 1. Kumpulkan seluruh berita baru dari SEMUA URL RSS
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if entry.link in sent_links:
                continue
                
            cleaned_title = clean_title(entry.title)
            if cleaned_title in sent_titles:
                continue
                
            raw_pub = entry.get('published', '')
            dt_wib = format_ke_wib(raw_pub)
            
            if dt_wib and dt_wib >= kemarin_12malam:
                is_match, matched_saham = is_target_saham(entry.title)
                
                if is_match:
                    source_name = entry.source.title if 'source' in entry else 'Google News'
                    pub_date_str = dt_wib.strftime("%d %b %Y, %H:%M WIB")
                    
                    sent_titles.add(cleaned_title)
                    collected_entries.append({
                        'title': entry.title,
                        'link': entry.link,
                        'source': source_name,
                        'pub_date_str': pub_date_str,
                        'matched_saham': matched_saham,
                        'dt_wib': dt_wib,
                        'cleaned_title': cleaned_title
                    })

    # 2. Urutkan secara presisi Kronologis (Terlama -> Terbaru)
    collected_entries.sort(key=lambda x: x['dt_wib'])

    # 3. Kirim ke Telegram satu per satu secara berurutan
    for item in collected_entries:
        if send_telegram(item['title'], item['link'], item['source'], item['pub_date_str'], item['matched_saham']):
            save_to_sheet(item['link'], item['cleaned_title'])
            sent_links.add(item['link'])
            time.sleep(1.5)

def main():
    print("Bot memantau berita saham di Render...")
    while True:
        try:
            check_and_send()
        except Exception as e:
            print(f"Error loop utama: {e}")
        time.sleep(600)

# --- 5. EKSEKUSI ---
if __name__ == "__main__":
    t = Thread(target=run)
    t.start()
    main()
