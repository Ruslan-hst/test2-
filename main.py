import os
import json
import base64
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
CREDS_B64 = os.environ["GOOGLE_CREDS_JSON_B64"]

creds_dict = json.loads(base64.b64decode(CREDS_B64).decode("utf-8"))
scopes = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).worksheet("Склад")
rows = sheet.get_all_records()
print(f"Загружено строк: {len(rows)}")
for r in rows:
    print(r)
