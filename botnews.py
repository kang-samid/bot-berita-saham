import feedparser, requests, time, gspread, json, os
from flask import Flask
from threading import Thread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 1. KONFIGURASI (Taruh di atas agar terbaca) ---
BOT_TOKEN = '6467585568:AAH_vmQvGa7bBDI-lfmPhEzq2R_4SqcRs-s'
CHAT_ID = '@Kang_Zeyen'
RSS_URL = 'https://news.google.com/rss/search?q=saham+OR+emiten+OR+"Bursa+Efek+Indonesia"+OR+IHSG+OR+Tbk+OR+investasi+OR+dividen+OR+"laporan+keuangan"+OR+IPO&hl=id&gl=ID&ceid=ID:id'

# --- 2. SETUP FLASK ---
app = Flask('')
@app.route('/')
def home(): return "Bot Sedang Aktif"

def run():
    app.run(host='0.0.0.0', port=8080)

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
    print("Bot sudah berjalan dan siap memantau berita!")
    while True:
        try:
            check_and_send()
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(600)

# --- 4. EKSEKUSI ---
if __name__ == "__main__":
    t = Thread(target=run)
    t.start()
    main()
