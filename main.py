import requests
import json
import os
from datetime import datetime

# 1. 텔레그램 정보 가져오기 (GitHub Secrets에서 안전하게 불러옵니다!)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FILE_NAME = "auction_data.json"

def send_telegram(message):
    """텔레그램 메시지 전송 함수"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={message}"
    requests.get(url)

def get_today_auction_data():
    # 수원 영통 / 용인 수지 가상 데이터
    data = {
        "2023타경1001 (영통동 벽적골)": 450000000, 
        "2023타경2002 (수지구 풍덕천동)": 600000000,
        "2024타경5555 (영통동 살구골)": 520000000
    }
    return data

# --- 메인 시스템 ---
print(f"🤖 [{datetime.now().strftime('%Y-%m-%d')}] 경매 봇 작동 시작...")

today_data = get_today_auction_data()

yesterday_data = {}
if os.path.exists(FILE_NAME):
    with open(FILE_NAME, "r", encoding="utf-8") as f:
        yesterday_data = json.load(f)
        print("📁 어제 저장된 데이터를 불러왔습니다.")
else:
    print("📁 첫 실행입니다. 비교할 과거 데이터가 없습니다.")

new_alerts = 0

for case_number, today_price in today_data.items():
    if case_number not in yesterday_data:
        msg = f"🚨 [신규 아파트 경매]\n📍 지역/사건: {case_number}\n💰 최저가: {today_price:,}원"
        send_telegram(msg)
        print(f" -> 신건 알림 전송: {case_number}")
        new_alerts += 1
        
    elif today_price < yesterday_data[case_number]:
        msg = f"📉 [유찰/가격하락 아파트]\n📍 지역/사건: {case_number}\n🔻 변경가: {yesterday_data[case_number]:,}원 ➡️ {today_price:,}원"
        send_telegram(msg)
        print(f" -> 유찰 알림 전송: {case_number}")
        new_alerts += 1

if new_alerts == 0:
    print("💤 변동 사항이 없습니다. 알림을 보내지 않습니다.")

with open(FILE_NAME, "w", encoding="utf-8") as f:
    json.dump(today_data, f, ensure_ascii=False, indent=4)
    print("💾 오늘의 경매 데이터를 파일에 저장했습니다.")

print("✅ 경매 봇 작동 완료!")
