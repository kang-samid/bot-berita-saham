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

KATA_UMUM = {"RAJA", "RATU", "EMAS", "BUMI", "BUKA", "DEWA", "WIFI", "ELSA", "CUAN", "MIKA", "INDY"}

KATA_RANGKUMAN = [
    "REKOMENDASI", "REKOMENDASIKAN", "IHSG", "TOP GAINERS", "TOP LOSERS", 
    "SOPING SAHAM", "KOLEKSI SAHAM", "PILAH-PILIH", "CERAH", "MERAH", 
    "KOMPAK", "POTENSI REBOUND", "CEK SAHAM", "DAFTAR SAHAM", "LAJU IHSG", "CUPON"
]

# ---------------------------------------------------------------------
# 🎯 ATURAN PENYARINGAN KHUSUS (Centralized Config)
# Tinggal tambah emiten di sini jika ada kasus serupa tanpa ubah logika kode!
# ---------------------------------------------------------------------
SPECIAL_FILTERS = {
    "ANTM": {
        "forbidden": ["HARGA EMAS", "LOGAM MULIA", "EMAS ANTAM", "HARGA JUAL EMAS", "EMAS DUNIA", "XAUUSD", "BUYBACK EMAS", "PERAK ANTAM", "HARGA PERAK", "PERAK HARI INI"],
        "required": ["SAHAM", "EMITEN", "TBK", "KINERJA", "LABA", "DIVIDEN", "IPO", "LAPORAN KEUANGAN", "PROSPEK", "PENDAPATAN", "OPERASIONAL", "TAMBANG"]
    },
    "RATU": {
        "forbidden": ["RATU DRAKOR", "RATU ELIZABETH", "DRAKOR", "SINOPSIS", "FILM", "SERIAL", "ARTIS", "PEMAIN"],
        "required": ["SAHAM", "EMITEN", "TBK", "RATU PRABU", "RED PLANET", "IHSG", "DIVIDEN", "BEI"]
    },
    "RAJA": {
        "forbidden": ["RAJA JULI", "RAJA AMPAT", "RAJA ARAB", "RAJA SAUDI"],
        "required": ["SAHAM", "EMITEN", "TBK", "RUKUN RAHARJA", "IHSG", "DIVIDEN", "BEI"]
    }
}

# --- 2. SETUP FLASK SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot News Saham Aktif di Render!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 3. SETUP GOOGLE SHEETS ---
scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def init_sheet():
    try:
        creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        return client.open("DatabaseBot").sheet1
    except Exception as e:
        print(f"Error Google Sheets: {e}")
        return None

sheet = init_sheet()

def get_sent_history():
    if not sheet: return set(), set()
    try:
        all_rows = sheet.get_all_values()
        return set(row[0] for row in all_rows if len(row) >= 1), set(row[1] for row in all_rows if len(row) >= 2)
    except Exception as e:
        print(f"Error get history: {e}")
        return set(), set()

def save_to_sheet(link, cleaned_title):
    if not sheet: return
    try:
        sheet.append_row([link, cleaned_title])
    except Exception as e:
        print(f"Error save sheet: {e}")

# --- 4. FUNGSI LOGIKA BOT ---
def clean_title(title):
    title_main = re.split(r'[-|]', title)[0]
    return re.sub(r'[^a-zA-Z0-9]', '', title_main).lower()

def generate_rss_urls(saham_list, chunk_size=15):
    urls = []
    for i in range(0, len(saham_list), chunk_size):
        chunk = saham_list[i:i + chunk_size]
        query_saham = "%20OR%20".join(chunk)
        urls.append(f'https://news.google.com/rss/search?q=({query_saham})&hl=id&gl=ID&ceid=ID:id')
    return urls

def format_ke_wib(published_str):
    try:
        dt = parsedate_to_datetime(published_str)
        return dt.astimezone(pytz.timezone('Asia/Jakarta'))
    except Exception:
        return None

def is_target_saham(title):
    title_upper = title.upper()

    # 1. Filter Rangkuman / Multi-emiten
    if any(kata in title_upper for kata in KATA_RANGKUMAN):
        return False, None

    matched_list = []
    konteks_generik = ["SAHAM", "EMITEN", "TBK", "DIVIDEN", "IPO", "LAPORAN KEUANGAN", "BURSA", "BEI", "IHSG"]

    # 2. Iterasi Emiten dengan Logika Dinamis
    for saham in TARGET_SAHAM:
        if re.search(rf'\b{saham}\b', title_upper):
            
            # Cek jika emiten punya aturan khusus di SPECIAL_FILTERS
            if saham in SPECIAL_FILTERS:
                rule = SPECIAL_FILTERS[saham]
                if any(bad in title_upper for bad in rule["forbidden"]):
                    # Jika ada kata terlarang, wajib ada salah satu kata positif/konteks
                    if not any(good in title_upper for good in rule["required"]):
                        continue  # Abaikan berita ini
            
            # Cek jika emiten masuk KATA_UMUM generik lainnya
            elif saham in KATA_UMUM:
                if not any(k in title_upper for k in konteks_generik):
                    continue

            matched_list.append(saham)

    # 3. Hanya loloskan jika persis 1 emiten
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
    payload = {"chat_id": CHAT_ID, "text": message_text, "parse_mode": "Markdown", "disable_web_page_preview": False}
    try:
        return requests.post(url, data=payload).status_code == 200
    except Exception:
        return False

def check_and_send():
    rss_urls = generate_rss_urls(TARGET_SAHAM, chunk_size=15)
    now_wib = datetime.now(pytz.timezone('Asia/Jakarta'))
    kemarin_12malam = (now_wib - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    sent_links, sent_titles = get_sent_history()
    collected_entries = []

    for url in rss_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if entry.link in sent_links: continue
                
            cleaned_title = clean_title(entry.title)
            if cleaned_title in sent_titles: continue
                
            dt_wib = format_ke_wib(entry.get('published', ''))
            
            if dt_wib and dt_wib >= kemarin_12malam:
                is_match, matched_saham = is_target_saham(entry.title)
                if is_match:
                    source_name = entry.source.title if 'source' in entry else 'Google News'
                    sent_titles.add(cleaned_title)
                    collected_entries.append({
                        'title': entry.title,
                        'link': entry.link,
                        'source': source_name,
                        'pub_date_str': dt_wib.strftime("%d %b %Y, %H:%M WIB"),
                        'matched_saham': matched_saham,
                        'dt_wib': dt_wib,
                        'cleaned_title': cleaned_title
                    })

    # Urutkan kronologis
    collected_entries.sort(key=lambda x: x['dt_wib'])

    # Kirim
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

if __name__ == "__main__":
    t = Thread(target=run)
    t.start()
    main()
