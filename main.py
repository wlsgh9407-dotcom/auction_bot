import os
import requests
import pandas as pd
import urllib.parse

# 텔레그램 설정값 불러오기 (GitHub Secrets)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def send_telegram_message(text):
    """텔레그램 메시지를 전송하는 함수"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 설정이 완료되지 않았습니다.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("텔레그램 전송 성공")
        else:
            print(f"텔레그램 전송 실패: {response.text}")
    except Exception as e:
        print(f"텔레그램 전송 중 오류 발생: {e}")

def get_target_auction_data(city, district):
    """지정된 도시와 구에 대한 아파트 경매 데이터를 수집합니다."""
    items = []
    
    # 한글을 다음 경매 사이트 규격(EUC-KR)에 맞추어 인코딩합니다.
    addr1_enc = urllib.parse.quote('경기', encoding='euc-kr')
    addr2_enc = urllib.parse.quote(city, encoding='euc-kr') # '수원시' 또는 '용인시'
    addr3_enc = urllib.parse.quote(district, encoding='euc-kr') # '영통구' 또는 '수지구'
    
    # 특정 시/구 검색이 적용된 정밀 주소 구성
    url = (
        "https://auction.realestate.daum.net/auction/search_detail.php"
        f"?addr1={addr1_enc}"
        f"&addr2={addr2_enc}"
        f"&addr3={addr3_enc}"
        "&result=%BD%C5%B0%C7%7C%C0%AF%C2%FB%7C%C1%F8%C7%E0"
        "&var_kind=111" # 아파트 고정
    )
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'euc-kr'
        
        dfs = pd.read_html(response.text)
        if not dfs:
            return items
            
        # 표 중에서 '사건번호'가 열 이름에 포함된 진짜 데이터 표 찾기
        df = None
        for table in dfs:
            if any('사건번호' in str(col) for col in table.columns):
                df = table
                break
                
        if df is None or df.empty:
            return items
            
        # 광고 및 불필요 행 데이터 정리
        df = df[df['사건번호'].notna()]
        df = df[df['사건번호'] != '가맹점신청']
        
        # 컬럼 이름의 띄어쓰기 오차 등을 해결하기 위한 유연한 컬럼 탐색
        col_case = [c for c in df.columns if '사건번호' in str(c)][0]
        col_detail = [c for c in df.columns if '상세정보' in str(c)][0]
        col_price = [c for c in df.columns if '감정가' in str(c)][0]
        col_date = [c for c in df.columns if '입찰' in str(c) or '결과' in str(c)][0]
        
        for _, row in df.iterrows():
            detail_info = str(row.get(col_detail, ''))
            
            # 주소 정보에 내가 찾는 구가 확실히 매칭되는지 재검증
            if district in detail_info:
                case_raw = str(row.get(col_case, '')).split()
                case_num = case_raw[0] if case_raw else "확인 필요"
                
                address = " ".join(detail_info.split())
                if address.startswith('아파트'):
                    address = address[3:].strip()
                address = f"경기도 {city} {address}"
                
                prices = str(row.get(col_price, '')).split('/')
                appraised = prices[0].strip() if len(prices) > 0 else "정보 없음"
                minimum = prices[1].strip() if len(prices) > 1 else "정보 없음"
                
                results_date = str(row.get(col_date, '')).split('/')
                status = results_date[0].strip() if len(results_date) > 0 else "진행"
                auc_date = results_date[1].strip() if len(results_date) > 1 else "미정"
                
                items.append({
                    "case_number": case_num,
                    "address": address,
                    "appraised_value": appraised,
                    "min_price": minimum,
                    "depreciated_count": status,
                    "auction_date": auc_date
                })
                
    except Exception as e:
        print(f"{city} {district} 경매 물건 조회 실패: {e}")
        
    return items

def main():
    print("수원시 영통구 및 용인시 수지구의 경매 정보를 개별 수집합니다...")
    
    # 두 개의 목표 지역 데이터를 각각 독립적으로 수집하여 병합합니다.
    target_items = []
    target_items.extend(get_target_auction_data("수원시", "영통구"))
    target_items.extend(get_target_auction_data("용인시", "수지구"))
    
    if not target_items:
        send_telegram_message("🔍 수원 영통 / 용인 수지 지역에 진행 중인 아파트 경매 물건이 존재하지 않습니다.")
        return
        
    message = "<b>📢 실시간 법원 경매 정보 (수원 영통 / 용인 수지 아파트)</b>\n"
    message += f"조회된 물건 수: {len(target_items)}건\n\n"
    
    for i, item in enumerate(target_items, 1):
        message += f"<b>{i}. {item['address']}</b>\n"
        message += f"• 사건번호: {item['case_number']}\n"
        message += f"• 감정가: {item['appraised_value']}\n"
        message += f"• 최저가: {item['min_price']} ({item['depreciated_count']})\n"
        message += f"• 매각기일: {item['auction_date']}\n\n"
        
    send_telegram_message(message)

if __name__ == "__main__":
    main()
