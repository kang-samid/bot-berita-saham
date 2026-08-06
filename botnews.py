import feedparserhttps://github.com/kang-samid/bot-berita-saham/blob/main/botnews.py
import requests
import time
import gspread
import json
import os
import re
from flask import Flask
from threading import Thread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from email.utils import parsedate_to_datetime
import pytz

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

# Ticker yang merupakan kata umum (membutuhkan validasi konteks ganda)
KATA_UMUM = {"RAJA", "RATU", "EMAS", "BUMI", "BUKA", "DEWA", "WIFI", "ELSA", "CUAN"}

# --- 2. SETUP FLASK (Server Keep-Alive) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot Sedang Aktif"

def run():
    app.run(host='0.0.0.0', port=8080)

# --- 3. SETUP GOOGLE SHEETS ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("DatabaseBot").sheet1

def get_sent_links():
    """Mengambil semua link yang sudah terkirim dari kolom A Google Sheets"""
    try:
        return set(sheet.col_values(1))
    except Exception as e:
        print(f"Error mengambil data dari Google Sheets: {e}")
        return set()

def save_to_sheet(link):
    """Menambah link baru ke baris paling bawah di Google Sheets"""
    try:
        sheet.append_row([link])
    except Exception as e:
        print(f"Error menyimpan ke Google Sheets: {e}")

# --- 4. FUNGSI LOGIKA BOT ---
def generate_rss_urls(saham_list, chunk_size=20):
    """Membagi 80 saham menjadi batch kecil (per 20 saham)"""
    urls = []
    for i in range(0, len(saham_list), chunk_size):
        chunk = saham_list[i:i + chunk_size]
        query_saham = "+OR+".join(chunk)
        url = f'https://news.google.com/rss/search?q={query_saham}&hl=id&gl=ID&ceid=ID:id'
        urls.append(url)
    return urls

def format_ke_wib(published_str):
    """Konversi string waktu RSS ke objek datetime berzona waktu WIB"""
    try:
        dt = parsedate_to_datetime(published_str)
        wib_tz = pytz.timezone('Asia/Jakarta')
        return dt.astimezone(wib_tz)
    except Exception:
        return None

def is_target_saham(title):
    """Penyaringan presisi dengan validasi kata umum dan regex boundary"""
    title_upper = title.upper()
    konteks_saham = ["SAHAM", "EMITEN", "TBK", "BEI", "IHSG", "DIVIDEN", "IPO", "BURSA", "LAPORAN KEUANGAN"]
    ada_konteks = any(k in title_upper for k in konteks_saham)
    
    for saham in TARGET_SAHAM:
        if re.search(rf'\b{saham}\b', title_upper):
            if saham in KATA_UMUM:
                if ada_konteks:
                    return True, saham
                else:
                    continue  # Abai jika berita non-saham
            return True, saham
            
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
    sent_links = get_sent_links()
    
    for url in rss_urls:
        feed = feedparser.parse(url)
        
        for entry in reversed(feed.entries):
            if entry.link in sent_links:
                continue
                
            raw_pub = entry.published if 'published' in entry else ''
            dt_wib = format_ke_wib(raw_pub)
            
            # Hanya memproses berita hari ini (WIB)
            if dt_wib and dt_wib.date() == now_wib.date():
                is_match, matched_saham = is_target_saham(entry.title)
                
                if is_match:
                    source_name = entry.source.title if 'source' in entry else 'Google News'
                    pub_date_str = dt_wib.strftime("%d %b %Y, %H:%M WIB")
                    
                    if send_telegram(entry.title, entry.link, source_name, pub_date_str, matched_saham):
                        save_to_sheet(entry.link)
                        sent_links.add(entry.link)
                        time.sleep(1.5)

def main():
    print("Bot sudah berjalan dan siap memantau berita!")
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
