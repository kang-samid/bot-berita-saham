from flask import Flask
from threading import Thread

# Flask kecil untuk menipu Render agar mengira ini adalah web service
app = Flask('')

@app.route('/')
def home():
    return "Bot Sedang Aktif"

def run():
    app.run(host='0.0.0.0', port=8080)

t = Thread(target=run)
t.start()

import feedparser
import requests
import time
import gspread
import json
import os
from flask import Flask
from threading import Thread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- Setup Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets', "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# Mengambil kredensial dari Environment Variable GOOGLE_CREDENTIALS
creds_dict = json.loads(os.environ['GOOGLE_CREDENTIALS'])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("DatabaseBot").sheet1

def get_sent_links():
    """Mengambil semua link yang sudah terkirim dari kolom A Google Sheets"""
    return set(sheet.col_values(1))

def save_to_sheet(link):
    """Menambah link baru ke baris paling bawah di Google Sheets"""
    sheet.append_row([link])

def send_telegram(title, link):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": f"📢 *{title}*\n\n🔗 {link}", "parse_mode": "Markdown"}
    requests.post(url, data=payload)

def check_and_send():
    print("Mengecek RSS feed...") # Tambahkan ini agar muncul di log
    feed = feedparser.parse(RSS_URL)
    today = datetime.now().strftime("%d %b %Y")
    sent_links = get_sent_links() # Ambil data terbaru dari Cloud
    
    for entry in reversed(feed.entries):
        if today in entry.published:
            if entry.link not in sent_links:
                print(f"Mengirim berita: {entry.title}")
                send_telegram(entry.title, entry.link)
                save_to_sheet(entry.link) # Simpan permanen ke Google Sheets
                sent_links.add(entry.link)
                time.sleep(2)

def main():
    while True:
        try:
            check_and_send()
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(600)

if __name__ == "__main__":
    print("Memulai bot...")
    
    # 1. Jalankan Flask di thread terpisah agar Render tidak protes
    t = Thread(target=run)
    t.start()
    
    # 2. Jalankan fungsi bot utama
    main()
