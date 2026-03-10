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
    """자산 유형별로 KIS API를 호출하여 현재가를 반환"""
    url = f"https://openapi.koreainvestment.com:9443/uapi/overseas-price/v1/quotations/price" # 기본 해외시세 URL
    
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": tr_id
    }
    
    # 국내 지수(KOSPI 등) 처리
    if tr_id == "FHPUP02100000":
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price"
        params = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": symbol}
        res = requests.get(url, headers=headers, params=params)
        return res.json()['output']['bstp_nmix_prpr']
    
    # 해외 지수 및 상품/환율 처리
    else:
        params = {"AUTH": "", "EXCD": excd, "SYMB": symbol}
        res = requests.get(url, headers=headers, params=params)
        res_data = res.json()
        if 'output' in res_data:
            return res_data['output']['last']
        return "N/A"

# 1. 추적할 지표 리스트 정의 (심볼은 KIS 표준 기준, 계정 권한에 따라 다를 수 있음)
# TR_ID 가이드: FHPST01020000(해외지수), FHPST01010000(해외종목/선물), FHPST04000000(환율)
targets = [
    {"name": "KOSPI", "tr_id": "FHPUP02100000", "symbol": "0001", "excd": ""},
    {"name": "나스닥", "tr_id": "FHPST01020000", "symbol": ".IXIC", "excd": "NAS"},
    {"name": "항셍", "tr_id": "FHPST01020000", "symbol": "HSI", "excd": "HKS"},
    {"name": "JPX Prime 150", "tr_id": "FHPST01020000", "symbol": "PRM150", "excd": "TSE"},
    {"name": "원달러 환율", "tr_id": "FHPST04000000", "symbol": "FX@USDKRW", "excd": "FX"},
    {"name": "엔 환율", "tr_id": "FHPST04000000", "symbol": "FX@JPYKRW", "excd": "FX"},
    {"name": "위안 환율", "tr_id": "FHPST04000000", "symbol": "FX@CNYKRW", "excd": "FX"},
    {"name": "유로 환율", "tr_id": "FHPST04000000", "symbol": "FX@EURKRW", "excd": "FX"},
    {"name": "달러인덱스", "tr_id": "FHPST01010000", "symbol": "DX", "excd": "NYM"},
    {"name": "WTI 원유", "tr_id": "FHPST01010000", "symbol": "CL", "excd": "NYM"},
    {"name": "골드 퓨쳐스", "tr_id": "FHPST01010000", "symbol": "GC", "excd": "CMX"},
    {"name": "천연가스선물", "tr_id": "FHPST01010000", "symbol": "NG", "excd": "NYM"},
    {"name": "미 10년물 국채금리", "tr_id": "FHPST01010000", "symbol": "US10Y", "excd": "cbt"},
    # 한국 국채는 API 권한에 따라 별도 tr_id가 필요할 수 있어 제외하거나 종목코드로 대체 가능
]

try:
    token = get_access_token()
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    # 구글 시트 연결
    creds_dict = json.loads(GSPREAD_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open("2026_Invest_Ledger").sheet1

    # 모든 지표 순회하며 수집 및 기록
    for target in targets:
        try:
            val = fetch_kis_data(token, target['tr_id'], target['symbol'], target['excd'])
            sheet.append_row([now, target['name'], val])
            print(f"✅ {target['name']}: {val} 기록 완료")
        except Exception as e:
            print(f"❌ {target['name']} 수집 실패: {e}")

    print(f"🚀 전체 데이터 업데이트 완료: {now}")

except Exception as e:
    print(f"🚨 치명적 오류 발생: {e}")
