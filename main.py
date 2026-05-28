import os
import requests
import pandas as pd

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

def scrape_real_auction_data():
    """다음 부동산 경매 페이지에서 실시간 경매 데이터를 가져와 필터링합니다."""
    items = []
    
    # 경기 지역(addr1=%B0%E2%B1%E2), 아파트(var_kind=111), 결과: 진행/유찰/신건 검색 URL
    url = (
        "https://auction.realestate.daum.net/auction/search_detail.php"
        "?addr1=%B0%E2%B1%E2"
        "&result=%BD%C5%B0%C7%7C%C0%AF%C2%FB%7C%C1%F8%C7%E0"
        "&var_kind=111"
    )
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        print("실시간 다음 부동산 경매 페이지를 호출합니다...")
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'euc-kr' # 다음 경매 웹페이지는 EUC-KR 인코딩을 사용합니다.
        
        # pandas를 이용해 웹페이지 내부의 테이블(표) 데이터를 리스트로 가져옵니다.
        dfs = pd.read_html(response.text)
        if not dfs:
            print("웹페이지에서 표 데이터를 찾지 못했습니다.")
            return items
            
        df = dfs[0]
        
        # 사건번호 컬럼 유효성 검사
        if '사건번호' not in df.columns:
            print("원하는 경매 표 구조가 아닙니다.")
            return items
            
        # 데이터 정제 (불필요한 공고 행 제거)
        df = df[df['사건번호'].notna()]
        df = df[df['사건번호'] != '가맹점신청'] # 가맹점 광고 행 제외
        
        for _, row in df.iterrows():
            detail_info = str(row.get('상세정보', ''))
            
            # 수원시 영통구 및 용인시 수지구 필터링
            if '수원시 영통구' in detail_info or '용인시 수지구' in detail_info:
                # 사건번호와 물건 번호가 뭉쳐있을 수 있으므로 공백 단위로 쪼개어 첫 번째 값만 가져옵니다.
                case_raw = str(row.get('사건번호', '')).split()
                case_num = case_raw[0] if case_raw else "확인 필요"
                
                # 상세정보에서 불필요한 공백을 제거하고 가독성 좋게 변환합니다.
                address = " ".join(detail_info.split())
                if address.startswith('아파트'): # 앞쪽의 불필요한 텍스트 제거
                    address = address[3:].strip()
                
                # 감정가, 최저가, 시세 정보 가공 (예: "1,200,000,000 / 840,000,000 / -")
                prices = str(row.get('감정가,최저가,시세', '')).split('/')
                appraised = prices[0].strip() if len(prices) > 0 else "정보 없음"
                minimum = prices[1].strip() if len(prices) > 1 else "정보 없음"
                
                # 결과(유찰 횟수 등) 및 매각기일 가공
                results_date = str(row.get('결과 / 입찰일', '')).split('/')
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
        print(f"크롤링 실행 중 에러가 발생했습니다: {e}")
        
    return items

def main():
    items = scrape_real_auction_data()
    
    if not items:
        send_telegram_message("🔍 수원 영통 / 용인 수지 지역에 오늘 진행 중인 아파트 경매 물건이 없습니다.")
        return
        
    message = "<b>📢 실시간 추천 법원 경매 물건 (수원 영통 / 용인 수지 아파트)</b>\n"
    message += f"오늘 조회된 전체 물건 수: {len(items)}건\n\n"
    
    for i, item in enumerate(items, 1):
        message += f"<b>{i}. {item['address']}</b>\n"
        message += f"• 사건번호: {item['case_number']}\n"
        message += f"• 감정가: {item['appraised_value']}\n"
        message += f"• 최저가: {item['min_price']} ({item['depreciated_count']})\n"
        message += f"• 매각기일: {item['auction_date']}\n\n"
        
    send_telegram_message(message)

if __name__ == "__main__":
    main()
