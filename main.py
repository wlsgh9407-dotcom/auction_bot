import os
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 텔레그램 설정값 불러오기 (GitHub Secrets)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("텔레그램 설정이 누락되었습니다.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"텔레그램 전송 중 오류 발생: {e}")

def get_official_court_data(start_date, end_date):
    items = []
    session = requests.Session()
    
    # 실제 브라우저와 100% 동일하게 헤더 구성
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://www.courtauction.go.kr',
        'Referer': 'https://www.courtauction.go.kr/InitMulSrch.laf',
    }
    
    try:
        print("1. 대법원 메인 서버 접속 (WMONID 보안 쿠키 발급 중)...")
        session.get('https://www.courtauction.go.kr/', headers=headers, timeout=10)
        
        print("2. 경매 검색 페이지 접속 (JSESSIONID 세션 연결 중)...")
        session.get('https://www.courtauction.go.kr/InitMulSrch.laf', headers=headers, timeout=10)
        
        print(f"3. 수원지방법원 관할 {start_date} ~ {end_date} 기일 아파트 정보를 요청합니다...")
        
        # 파이썬의 자동 인코딩 오류를 원천 차단하기 위해 대법원이 쓰는 EUC-KR Raw String 폼 데이터를 직접 꽂아 넣습니다.
        data_string = (
            "bubwLocGubun=1&"
            "jiwonNm=%BC%F6%BF%F8%C1%F6%B9%E6%B9%FD%BF%F8&" # '수원지방법원'
            "jpDeptCd=000000&"
            "daepyoSidoCd=&"
            "daepyoSiguCd=&"
            "daepyoDongCd=&"
            "notifyLoc=on&"
            "notifyRealRoad=on&"
            "ipchalGbncd=000331&"
            f"termStartDt={start_date}&"
            f"termEndDt={end_date}&"
            "lclsUtilCd=0000802&"
            "mclsUtilCd=000080201&"
            "sclsUtilCd=00008020104&"
            "_FORM_YN=Y&"
            "_CUR_CMD=InitMulSrch.laf&"
            "_CUR_SRNID=PNO102001&"
            "_NEXT_CMD=RetrieveRealEstMulDetailList.laf&"
            "_NEXT_SRNID=PNO102002"
        )
        
        response = session.post(
            'https://www.courtauction.go.kr/RetrieveRealEstMulDetailList.laf',
            headers=headers,
            data=data_string,
            timeout=15
        )
        response.encoding = 'euc-kr'
        
        # ----------------- [스마트 진단 및 예외 처리] -----------------
        try:
            dfs = pd.read_html(StringIO(response.text))
            
            if not dfs:
                raise ValueError("표(table)를 찾을 수 없음")
                
            df = None
            for table in dfs:
                if any('사건번호' in str(col) for col in table.columns):
                    df = table
                    break
                    
            if df is None or df.empty:
                raise ValueError("유효한 사건번호 표를 찾을 수 없음")
                
        except ValueError:
            # 대법원 서버가 물건 표 대신 차단 화면이나 오류를 띄웠을 경우 그 내용을 뽑아서 텔레그램으로 쏩니다.
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style"]):
                script.extract()
            text_preview = soup.get_text(separator=' ', strip=True)[:300]
            
            if "결과가 없습니다" in text_preview or "사건이 없습니다" in text_preview:
                print("조건에 맞는 물건이 0건입니다.")
                return items
                
            error_msg = (
                f"❌ <b>대법원 크롤링 서버 응답 분석 결과</b>\n"
                f"정상적인 표를 불러오지 못했습니다. 아래 응답을 확인해주세요.\n\n"
                f"[서버 화면에 적힌 실제 텍스트]:\n{text_preview}"
            )
            send_telegram_message(error_msg)
            print("에러 발생: 텔레그램으로 대법원 서버의 실제 응답 텍스트를 전송했습니다.")
            return items
            
        # 정상적으로 표를 찾은 경우 필터링 작업 시작
        col_case = [c for c in df.columns if '사건번호' in str(c)][0]
        col_detail = [c for c in df.columns if '소재지' in str(c)][0]
        col_price = [c for c in df.columns if '감정' in str(c) or '최저' in str(c)][0]
        col_date = [c for c in df.columns if '기일' in str(c) or '상태' in str(c)][0]
        
        df = df[df[col_case].notna()]
        
        for _, row in df.iterrows():
            case_text = str(row.get(col_case, ''))
            detail_text = str(row.get(col_detail, ''))
            
            # 수원지방법원 전체 매물 중 '영통구'와 '수지구'만 정확하게 낚아챕니다.
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
        print(f"시스템 시스템 에러: {e}")
        send_telegram_message(f"❌ <b>파이썬 코드 시스템 에러</b>\n{str(e)}")
        
    return items

def main():
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9)
    
    start_date = now_kst.strftime('%Y.%m.%d')
    end_date = (now_kst + timedelta(days=14)).strftime('%Y.%m.%d')
    
    target_items = get_official_court_data(start_date, end_date)
    
    if not target_items:
        # 스마트 진단에서 이미 에러 메시지를 보냈다면 중복 발송 생략
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
