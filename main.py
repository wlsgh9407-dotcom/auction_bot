import os
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import urllib.parse # EUC-KR 인코딩용 표준 라이브러리

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

def get_official_court_data(start_date, end_date):
    """
    대한민국 법원 공식 경매 사이트(courtauction.go.kr)에서 
    수원지방법원 관할의 전체 아파트 경매 정보를 일괄 수집한 후 정밀 선별합니다.
    """
    items = []
    session = requests.Session()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://www.courtauction.go.kr',
        'Referer': 'https://www.courtauction.go.kr/InitMulSrch.laf',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    
    try:
        print("대법원 메인 세션을 연결하는 중...")
        # 1. 세션 쿠키 획득
        session.get('https://www.courtauction.go.kr/InitMulSrch.laf', headers=headers, timeout=10)
        
        # 2. 수원지방법원 관할 전체 아파트를 조회하는 대법원 규격 폼 구성
        data = {
            'bubwLocGubun': '1',              # 1: 법원별 검색 옵션 (가장 확실하고 누락이 없습니다)
            'jiwonNm': '수원지방법원',        # 관할 법원 지정 (이후 EUC-KR로 인코딩되어 전송됨)
            'jpDeptCd': '000000',
            'daepyoSidoCd': '',
            'daepyoSiguCd': '',
            'daepyoDongCd': '',
            'notifyLoc': 'on',
            'rd1Cd': '',
            'rd2Cd': '',
            'realVowel': '',
            'rd3Rd4Cd': '',
            'notifyRealRoad': 'on',
            'saYear': '',
            'saSer': '',
            'ipchalGbncd': '000331',          # 기일입찰 방식 고정
            'termStartDt': start_date,        # 조회 시작일 (당일)
            'termEndDt': end_date,            # 조회 종료일 (2주 뒤)
            'lclsUtilCd': '0000802',          # 건물 > 주거용건물
            'mclsUtilCd': '000080201',        # 공동주택
            'sclsUtilCd': '00008020104',      # 아파트
            'gamEvalAmtGuganMin': '',
            'gamEvalAmtGuganMax': '',
            'notifyMinMgakPrcMin': '',
            'notifyMinMgakPrcMax': '',
            'areaGuganMin': '',
            'areaGuganMax': '',
            'yuchalCntGuganMin': '',
            'yuchalCntGuganMax': '',
            'notifyMinMgakPrcRateMin': '',
            'notifyMinMgakPrcRateMax': '',
            'srchJogKindcd': '',
            'mvRealGbncd': '00031R',
            'srnID': 'PNO102001',
            '_NAVI_CMD': '',
            '_NAVI_SRNID': '',
            '_SRCH_SRNID': 'PNO102001',
            '_CUR_CMD': 'InitMulSrch.laf',
            '_CUR_SRNID': 'PNO102001',
            '_NEXT_CMD': 'RetrieveRealEstMulDetailList.laf',
            '_NEXT_SRNID': 'PNO102002',
            '_PRE_SRNID': '',
            '_LOGOUT_CHK': '',
            '_FORM_YN': 'Y'
        }
        
        # [핵심 디버깅 포인트] 
        # 파이썬 requests는 기본적으로 폼 데이터를 UTF-8로 인코딩합니다.
        # 법원 사이트의 한글 처리를 통과하려면 반드시 아래처럼 수동으로 EUC-KR로 url인코딩해서 보냐야 정상 작동합니다.
        encoded_data = urllib.parse.urlencode(data, encoding='euc-kr')
        
        print(f"수원지방법원 관할 {start_date} ~ {end_date} 기일 아파트 경매 정보를 수집합니다...")
        response = session.post(
            'https://www.courtauction.go.kr/RetrieveRealEstMulDetailList.laf',
            headers=headers,
            data=encoded_data, # EUC-KR 바이트 전송
            timeout=15
        )
        response.encoding = 'euc-kr'
        
        # 3. 만약 대법원 방화벽 등에 완전히 IP 차단이 일어난 경우 디버깅용 로그 남기기
        if "자동입력방지" in response.text or "안전한 서비스 이용" in response.text or "보안문자" in response.text:
            print("🚨 대법원 방화벽이 가상 서버의 IP를 일시적으로 차단하여 보안 인증 화면을 띄웠습니다.")
            return items
            
        # 4. Pandas로 HTML 테이블 파싱
        try:
            dfs = pd.read_html(StringIO(response.text))
        except ValueError:
            print("테이블 데이터를 찾지 못했습니다. (조회 결과가 없거나 페이지 파싱 실패)")
            return items
            
        if not dfs:
            return items
            
        df = None
        for table in dfs:
            if any('사건번호' in str(col) for col in table.columns):
                df = table
                break
                
        if df is None or df.empty:
            return items
            
        # 열 매핑 찾기
        col_case = [c for c in df.columns if '사건번호' in str(c)][0]
        col_detail = [c for c in df.columns if '소재지' in str(c)][0]
        col_price = [c for c in df.columns if '감정' in str(c) or '최저' in str(c)][0]
        col_date = [c for c in df.columns if '기일' in str(c) or '상태' in str(c)][0]
        
        df = df[df[col_case].notna()]
        
        for _, row in df.iterrows():
            case_text = str(row.get(col_case, ''))
            detail_text = str(row.get(col_detail, ''))
            
            # [필터링 고도화] 수원지방법원 관할 전체 중 '수원시 영통구' 및 '용인시 수지구'가 주소에 포함된 매물만 선별합니다.
            if ('수원시 영통구' in detail_text) or ('용인시 수지구' in detail_text):
                case_raw = case_text.split()
                case_num = case_raw[0] if case_raw else "확인 필요"
                
                address = " ".join(detail_text.split())
                
                price_text = " ".join(str(row.get(col_price, '')).split())
                prices = price_text.split()
                appraised = prices[0] if len(prices) > 0 else "정보 없음"
                minimum = prices[1] if len(prices) > 1 else "정보 없음"
                
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
        print(f"크롤링 실행 중 예외 발생: {e}")
        
    return items

def main():
    print("대한민국 법원 공식 경매 정보를 다이렉트로 수집합니다...")
    
    # 한국 표준시(KST) 조회 기간 계산 (당일 ~ 2주 뒤)
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9)
    
    start_date = now_kst.strftime('%Y.%m.%d')                      # 오늘 날짜
    end_date = (now_kst + timedelta(days=14)).strftime('%Y.%m.%d')  # 2주 뒤 날짜
    
    target_items = get_official_court_data(start_date, end_date)
    
    if not target_items:
        send_telegram_message(f"🔍 [{start_date} ~ {end_date}] 기간 내에 수원 영통 / 용인 수지 지역의 아파트 경매 진행 물건이 존재하지 않습니다.")
        return
        
    message = f"<b>📢 법원 경매 정보 ({start_date} ~ {end_date} 기일)</b>\n"
    message += f"조회 조건: 경기도 수원 영통 / 용인 수지 (아파트)\n"
    message += f"해당 기간 내 진행 물건 수: {len(target_items)}건\n\n"
    
    for i, item in enumerate(target_items, 1):
        message += f"<b>{i}. {item['address']}</b>\n"
        message += f"• 사건번호: {item['case_number']}\n"
        message += f"• 감정가: {item['appraised_value']}\n"
        message += f"• 최저가: {item['min_price']} ({item['depreciated_count']})\n"
        message += f"• 매각기일: {item['auction_date']}\n\n"
        
    send_telegram_message(message)

if __name__ == "__main__":
    main()
