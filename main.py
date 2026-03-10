import os
import json
import requests
import gspread
from datetime import datetime
import pytz
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

def fetch_kis_data(token, tr_id, symbol, excd=""):
    """자산 유형별 현재가 수집"""
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id
    }
    
    if tr_id == "FHPUP02100000": # 국내 지수
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price"
        params = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": symbol}
        res = requests.get(url, headers=headers, params=params)
        return res.json().get('output', {}).get('bstp_nmix_prpr', "N/A")
    
    else: # 해외 지수, 선물, 환율
        url = "https://openapi.koreainvestment.com:9443/uapi/overseas-price/v1/quotations/price"
        params = {"AUTH": "", "EXCD": excd, "SYMB": symbol}
        res = requests.get(url, headers=headers, params=params)
        return res.json().get('output', {}).get('last', "N/A")

try:
    # 1. 인증 및 시트 연결
    token = get_access_token()
    creds_dict = json.loads(GSPREAD_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    
    spreadsheet = client.open("2026_Invest_Ledger")
    config_sheet = spreadsheet.worksheet("Config")
    log_sheet = spreadsheet.get_worksheet(0) # 첫 번째 시트(데이터 기록용)

    # 2. Config 시트에서 수집 대상 리스트 읽기
    # get_all_records()는 첫 줄을 헤더로 인식하여 딕셔너리 리스트를 만듭니다.
    targets = config_sheet.get_all_records()
    print(f"📊 수집 대상 {len(targets)}건 확인 완료")

    # 3. 데이터 수집 및 기록
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    for target in targets:
        name = target.get('Name')
        tr_id = str(target.get('TR_ID'))
        symbol = str(target.get('Symbol')).zfill(4) if tr_id == "FHPUP02100000" else str(target.get('Symbol'))
        excd = str(target.get('EXCD', ''))
        
        if not name or not tr_id or not symbol:
            continue

        try:
            val = fetch_kis_data(token, tr_id, symbol, excd)
            log_sheet.append_row([now, name, val])
            print(f"✅ {name}: {val} 기록 완료")
        except Exception as e:
            print(f"❌ {name} 수집 실패: {e}")

    print(f"🚀 전체 데이터 업데이트 완료: {now}")

except Exception as e:
    print(f"🚨 치명적 오류 발생: {e}")
