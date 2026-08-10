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
  "BUKA", "BUMI", "CBDK", "CMRY", "CPIN", "CTRA", "CUAN", "DEWA", "DSNG", "ELSA",
  "EMTK", "ENRG", "ERAA", "ESSA", "EXCL", "GGRM", "GOTO", "HEAL", "HRTA", "HRUM",
  "ICBP", "INCO", "INDF", "INDY", "INKP", "ISAT", "ITMG", "JPFA", "JSMR", "KIJA",
  "KLBF", "KPIG", "LSIP", "MAPA", "MAPI", "MBMA", "MDKA", "MEDC", "MIKA", "MYOR",
  "NCKL", "PGAS", "PGEO", "PNLF", "PTBA", "PTRO", "PWON", "RAJA", "RATU", "SCMA",
  "SMGR", "SMRA", "SSIA", "TAPG", "TLKM", "TOWR", "TPIA", "UNTR", "UNVR", "WIFI"
]

# Ticker berupa kata umum (butuh konteks saham)
KATA_UMUM = {"RAJA", "RATU", "EMAS", "BUMI", "BUKA", "DEWA", "WIFI", "ELSA", "CUAN", "MIKA", "INDY"}

# Kata kunci penyaring RANGKUMAN / MULTI-EMITEN
KATA_RANGKUMAN = [
    "REKOMENDASI", "REKOMENDASIKAN", "IHSG", "TOP GAINERS", "TOP LOSERS", 
    "SOPING SAHAM", "KOLEKSI SAHAM", "PILAH-PILIH", "CERAH", "MERAH", 
    "KOMPAK", "POTENSI REBOUND", "CEK SAHAM", "DAFTAR SAHAM", "LAJU IHSG", "CUPON"
]

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

def get_sent_links():
    if not sheet:
        return set()
    try:
        return set(sheet.col_values(1))
    except Exception as e:
        print(f"Error mengambil data sheet: {e}")
        return set()

def save_to_sheet(link):
    if not sheet:
        return
    try:
        sheet.append_row([link])
    except Exception as e:
        print(f"Error menyimpan ke sheet: {e}")

# --- 4. FUNGSI LOGIKA BOT ---
def clean_title(title):
    """
    Membersihkan judul agar berita dengan judul mirip/sama dianggap identik:
    1. Membuang nama sumber berita di akhir judul (misal: '... - Detikcom' / '... | Antara')
    2. Menghapus tanda baca & mengubah ke huruf kecil
    """
    title_main = re.split(r'[-|]', title)[0]  # Ambil bagian utama judul saja
    return re.sub(r'[^a-zA-Z0-9]', '', title_main).lower()

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
    konteks_saham = ["SAHAM", "EMITEN", "TBK", "DIVIDEN", "IPO", "LAPORAN KEUANGAN"]
    ada_konteks = any(k in title_upper for k in konteks_saham)
    
    matched_list = []
    for saham in TARGET_SAHAM:
        if re.search(rf'\b{saham}\b', title_upper):
            if saham in KATA_UMUM:
                if ada_konteks:
                    matched_list.append(saham)
            else:
                matched_list.append(saham)

    # 3. Hanya ambil jika persis 1 emiten
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
    
    # Memantau berita sejak kemarin jam 00:00 WIB
    kemarin_12malam = (now_wib - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    sent_links = get_sent_links()
    collected_entries = []
    seen_titles = set()  # Set untuk memfilter judul duplikat

    # 1. Kumpulkan Berita
    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if entry.link in sent_links:
                continue
                
            # Filter Judul Duplikat
            cleaned_title = clean_title(entry.title)
            if cleaned_title in seen_titles:
                continue
                
            raw_pub = entry.published if 'published' in entry else ''
            dt_wib = format_ke_wib(raw_pub)
            
            if dt_wib and dt_wib >= kemarin_12malam:
                is_match, matched_saham = is_target_saham(entry.title)
                
                if is_match:
                    source_name = entry.source.title if 'source' in entry else 'Google News'
                    pub_date_str = dt_wib.strftime("%d %b %Y, %H:%M WIB")
                    
                    seen_titles.add(cleaned_title)  # Tandai judul sebagai sudah diproses
                    collected_entries.append({
                        'title': entry.title,
                        'link': entry.link,
                        'source': source_name,
                        'pub_date_str': pub_date_str,
                        'matched_saham': matched_saham,
                        'dt_wib': dt_wib
                    })

    # 2. Urutkan Kronologis (Terlama -> Terbaru)
    collected_entries.sort(key=lambda x: x['dt_wib'])

    # 3. Kirim ke Telegram
    for item in collected_entries:
        if send_telegram(item['title'], item['link'], item['source'], item['pub_date_str'], item['matched_saham']):
            save_to_sheet(item['link'])
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
