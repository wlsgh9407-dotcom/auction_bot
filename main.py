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

def get_official_court_data(sigungu_code, city, district):
    """대한민국 법원 공식 경매 사이트(courtauction.go.kr)에서 실시간 아파트 경매 정보를 직접 수집합니다."""
    items = []
    
    # 쿠키와 세션을 관리하기 위한 Session 객체 생성
    session = requests.Session()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://www.courtauction.go.kr',
        'Referer': 'https://www.courtauction.go.kr/InitMulSrch.laf',
    }
    
    try:
        print(f"대법원 시스템에서 {city} {district} 경매 데이터를 요청하는 중...")
        
        # 1. 먼저 메인 검색 페이지에 한번 접속하여 세션 쿠키(JSESSIONID 등)를 정상적으로 발급받습니다.
        session.get('https://www.courtauction.go.kr/InitMulSrch.laf', headers=headers, timeout=10)
        
        # 2. 법원경매 검색 엔진에 직접 전달할 POST 데이터를 구성합니다.
        data = {
            'bubwLocGubun': '2',          # 2: 지역구분 검색 옵션
            'daepyoSidoCd': '41',         # 41: 경기도
            'daepyoSiguCd': sigungu_code, # 41117(영통구) 또는 41465(수지구)
            'ipchalGbncd': '000331',      # 기일입찰 방식 고정
            'lclsUtilCd': '0000802',      # 아파트 대분류
            'mclsUtilCd': '000080201',    # 공동주택 중분류
            'sclsUtilCd': '00008020104',  # 아파트 소분류
            'mvRealGbncd': '00031R',
            '_FORM_YN': 'Y',
            '_CUR_CMD': 'InitMulSrch.laf',
            '_NEXT_CMD': 'RetrieveRealEstMulDetailList.laf'
        }
        
        # 3. 실시간 경매 상세 정보 목록 요청
        response = session.post(
            'https://www.courtauction.go.kr/RetrieveRealEstMulDetailList.laf',
            headers=headers,
            data=data,
            timeout=15
        )
        response.encoding = 'euc-kr' # 대한민국 법원 시스템은 euc-kr 인코딩을 사용합니다.
        
        # 4. pandas를 사용해 수신된 HTML 문서의 경매 표 데이터 프레임을 추출합니다.
        dfs = pd.read_html(response.text)
        if not dfs:
            return items
            
        # '사건번호' 컬럼이 표 안에 있는지 안전하게 확인하며 경매 표를 선택합니다.
        df = None
        for table in dfs:
            if any('사건번호' in str(col) for col in table.columns):
                df = table
                break
                
        if df is None or df.empty:
            return items
            
        # 컬럼 이름의 공백이나 특수문자 오차를 극복하기 위한 유연한 컬럼명 조회
        col_case = [c for c in df.columns if '사건번호' in str(c)][0]
        col_detail = [c for c in df.columns if '소재지' in str(c)][0]
        col_price = [c for c in df.columns if '감정' in str(c) or '최저' in str(c)][0]
        col_date = [c for c in df.columns if '기일' in str(c) or '상태' in str(c)][0]
        
        # 데이터 정제 및 사건번호 결측값 행 제외
        df = df[df[col_case].notna()]
        
        for _, row in df.iterrows():
            case_text = str(row.get(col_case, ''))
            detail_text = str(row.get(col_detail, ''))
            
            # 주소 정보에 내가 찾는 구가 포함되어 있는지 마지막으로 더블 체크합니다.
            if district in detail_text:
                # 사건번호와 아파트 등의 물건 번호 텍스트 분리
                case_raw = case_text.split()
                case_num = case_raw[0] if case_raw else "확인 필요"
                
                # 주소 가독성 공백 제거 가공
                address = " ".join(detail_text.split())
                
                # 감정가 및 최저매각가격 정보 정제 (대법원 표는 한 칸에 줄바꿈으로 같이 표현됨)
                price_text = " ".join(str(row.get(col_price, '')).split())
                prices = price_text.split()
                appraised = prices[0] if len(prices) > 0 else "정보 없음"
                minimum = prices[1] if len(prices) > 1 else "정보 없음"
                
                # 매각기일 및 진행 상태 정보 정제
                date_text = " ".join(str(row.get(col_date, '')).split())
                dates_status = date_text.split()
                status = dates_status[1] if len(dates_status) > 1 else "진행"
                auc_date = dates_status[0] if len(dates_status) > 0 else "미정"
                
                items.append({
                    "case_number": case_num,
                    "address": address,
                    "appraised_value": appraised,
                    "min_price": minimum,
                    "depreciated_count": status,
                    "auction_date": auc_date
                })
                
    except Exception as e:
        print(f"{city} {district} 법원 정보 크롤링 중 오류: {e}")
        
    return items

def main():
    print("대한민국 법원 공식 경매 정보를 다이렉트로 수집합니다...")
    
    target_items = []
    # 수원시 영통구(41117) 및 용인시 수지구(41465) 경매 아파트를 수집합니다.
    target_items.extend(get_official_court_data("41117", "수원시", "영통구"))
    target_items.extend(get_official_court_data("41465", "용인시", "수지구"))
    
    if not target_items:
        send_telegram_message("🔍 수원 영통 / 용인 수지 지역에 현재 법원에 진행 중인 아파트 경매 물건이 없습니다.")
        return
        
    message = "<b>📢 실시간 법원 경매 정보 (수원 영통 / 용인 수지 아파트)</b>\n"
    message += f"현재 법원에 진행 중인 물건: {len(target_items)}건\n\n"
    
    for i, item in enumerate(target_items, 1):
        message += f"<b>{i}. {item['address']}</b>\n"
        message += f"• 사건번호: {item['case_number']}\n"
        message += f"• 감정가: {item['appraised_value']}\n"
        message += f"• 최저가: {item['min_price']} ({item['depreciated_count']})\n"
        message += f"• 매각기일: {item['auction_date']}\n\n"
        
    send_telegram_message(message)

if __name__ == "__main__":
    main()
