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
    params = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": str(symbol).zfill(4)}
    res = requests.get(url, headers=headers, params=params)
    return res.json().get('output', {}).get('bstp_nmix_prpr', "N/A")

# 🎯 [신규 추가] 한국투자증권 API: 국내 개별 주식 가격 조회 전용 함수
def fetch_kis_stock(token, symbol):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100"
    }
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": str(symbol).zfill(6) # 주식 코드는 항상 6자리
    }
    res = requests.get(url, headers=headers, params=params)
    return res.json().get('output', {}).get('stck_prpr', "N/A")

def fetch_yf_data(symbol):
    """야후 파이낸스: 해외 지수, 환율, 원자재 전용"""
    try:
        ticker = yf.Ticker(symbol)
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
    holdings_sheet = spreadsheet.get_worksheet(1)  # 🎯 2번째 시트 지정
    log_sheet = spreadsheet.get_worksheet(0)

    # 2. 수집 대상 리스트 읽기 및 병합
    targets = []
    
    # 2-1. 거시 지표 추가 (Config 시트)
    config_records = config_sheet.get_all_records()
    for row in config_records:
        name = row.get('Name')
        symbol = str(row.get('Symbol', ''))
        if name and symbol:
            targets.append({
                'Name': name,
                'TR_ID': str(row.get('TR_ID', '')),
                'Symbol': symbol
            })
            
    # 2-2. 개별 보유 종목 추가 (Asset_Holdings_Status 시트)
    holding_records = holdings_sheet.get_all_records()
    for row in holding_records:
        name = row.get('Name') or row.get('name') or row.get('종목명') or row.get('자산명')
        ticker = row.get('Ticker') or row.get('ticker') or row.get('Symbol') or row.get('종목코드')
        
        if name and ticker:
            targets.append({
                'Name': str(name),
                'TR_ID': 'STOCK',
                'Symbol': str(ticker).zfill(6)
            })

    print(f"📊 수집 대상 총 {len(targets)}건 병합 완료 (거시지표 + 개별주식)")

    # 3. 데이터 수집
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    new_rows = []
    
    for target in targets:
        name = target.get('Name')
        tr_id = target.get('TR_ID')
        symbol = target.get('Symbol')

        try:
            # TR_ID에 따라 알맞은 API 함수 분기
            if "FHPUP" in tr_id:
                val = fetch_kis_kospi(token, symbol)
            elif tr_id == "STOCK":
                # 🎯 [신규 추가] 개별 주식은 별도 함수로 호출
                val = fetch_kis_stock(token, symbol)
            else:
                val = fetch_yf_data(symbol)
                
            new_rows.append([now, name, val])
            print(f"✅ {name}: {val} 수집 완료")
        except Exception as e:
            print(f"❌ {name} 수집 실패: {e}")

    # 4. 시트 최상단(헤더 바로 아래, 즉 2행)에 일괄 삽입
    if new_rows:
        log_sheet.insert_rows(new_rows, row=2)
        print(f"🚀 최상단(2행) 데이터 일괄 삽입 완료: {now}")

except Exception as e:
    print(f"🚨 치명적 오류 발생: {e}")
