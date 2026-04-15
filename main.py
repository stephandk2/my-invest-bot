import os
import json
import requests
import gspread
from datetime import datetime
import pytz
import yfinance as yf
from oauth2client.service_account import ServiceAccountCredentials

# 환경 변수 로드
APP_KEY = os.environ.get("KIS_APP_KEY")
APP_SECRET = os.environ.get("KIS_APP_SECRET")
GSPREAD_JSON = os.environ.get("GSPREAD_JSON")

def get_access_token():
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    payload = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    headers = {"Content-Type": "application/json; charset=UTF-8"}
    res = requests.post(url, headers=headers, json=payload)
    return res.json().get("access_token")

def fetch_kis_kospi(token, symbol):
    """한국투자증권 API: 국내 지수 전용"""
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPUP02100000"
    }
    # 모바일 시트에서 '1'로 입력되어도 '0001'로 안전하게 변환
    params = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": str(symbol).zfill(4)}
    res = requests.get(url, headers=headers, params=params)
    return res.json().get('output', {}).get('bstp_nmix_prpr', "N/A")

def fetch_yf_data(symbol):
    """야후 파이낸스: 해외 지수, 환율, 원자재 전용"""
    try:
        ticker = yf.Ticker(symbol)
        # 당일(또는 직전 거래일)의 종가를 가져옵니다
        todays_data = ticker.history(period='1d')
        if not todays_data.empty:
            return round(todays_data['Close'].iloc[0], 2)
        return "N/A"
    except Exception as e:
        print(f"⚠️ 야후 파이낸스 조회 오류 ({symbol}): {e}")
        return "N/A"

try:
    # 1. KIS 인증 및 시트 연결
    token = get_access_token()
    creds_dict = json.loads(GSPREAD_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    
    spreadsheet = client.open("2026_Invest_Ledger")
    config_sheet = spreadsheet.worksheet("Config")
    log_sheet = spreadsheet.get_worksheet(0)

    # 2. 수집 대상 리스트 읽기
    targets = config_sheet.get_all_records()
    print(f"📊 수집 대상 {len(targets)}건 확인 완료")

    # 3. 데이터 수집
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    # 추가된 부분: 삽입할 데이터를 모아둘 리스트
    new_rows = []
    
    for target in targets:
        name = target.get('Name')
        tr_id = str(target.get('TR_ID', ''))
        symbol = str(target.get('Symbol', ''))
        
        if not name or not symbol:
            continue

        try:
            # TR_ID가 KOSPI 코드면 KIS API 호출, 아니면 야후 파이낸스 호출
            if "FHPUP" in tr_id:
                val = fetch_kis_kospi(token, symbol)
            else:
                val = fetch_yf_data(symbol)
                
            # append_row 대신 new_rows 리스트에 데이터 적재
            new_rows.append([now, name, val])
            print(f"✅ {name}: {val} 수집 완료")
        except Exception as e:
            print(f"❌ {name} 수집 실패: {e}")

    # 4. 시트 최상단(헤더 바로 아래, 즉 2행)에 일괄 삽입 (API 호출 최적화)
    if new_rows:
        # new_rows를 넣으면 2행부터 차례대로 밀어넣습니다.
        log_sheet.insert_rows(new_rows, row=2)
        print(f"🚀 최상단(2행) 데이터 일괄 삽입 완료: {now}")

except Exception as e:
    print(f"🚨 치명적 오류 발생: {e}")
