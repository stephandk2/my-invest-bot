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
    base_url = "https://openapi.koreainvestment.com:9443" 
    url = f"{base_url}/oauth2/tokenP"
    payload = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET  
    }
    headers = {"Content-Type": "application/json; charset=UTF-8"}
    
    print(f"DEBUG: 토큰 발급 시도 중... (URL: {url})")
    res = requests.post(url, headers=headers, data=json.dumps(payload))
    res_data = res.json()
    
    if "access_token" not in res_data:
        print(f"❌ 토큰 발급 실패: {json.dumps(res_data, indent=2, ensure_ascii=False)}")
        raise Exception("Access Token 발급 실패")
        
    print("✅ 토큰 발급 성공")
    return res_data["access_token"]

# 메인 실행부
try:
    token = get_access_token()
    
    # KOSPI 지수 조회
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {
        "Content-Type": "application/json", 
        "authorization": f"Bearer {token}", 
        "appkey": APP_KEY, 
        "appsecret": APP_SECRET,
        "tr_id": "FHPUP02100000"
    }
    # 실수로 지워졌던 params 부분입니다.
    params = {
        "fid_cond_mrkt_div_code": "U", 
        "fid_input_iscd": "0001"
    }
    
    res = requests.get(url, headers=headers, params=params)
    res_data = res.json()
    
    # 'output' 상자가 없으면 증권사가 보낸 진짜 에러 메시지를 출력합니다.
    if 'output' not in res_data:
        print(f"❌ KOSPI 조회 거절됨. 증권사 응답 내용:\n{json.dumps(res_data, indent=2, ensure_ascii=False)}")
        raise Exception("코스피 데이터 수신 실패")
        
    kospi = res_data['output']['bstp_nmix_prpr']

    # 구글 시트 기록
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    creds_dict = json.loads(GSPREAD_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    sheet = client.open("2026_Invest_Ledger").sheet1
    
    sheet.append_row([now, "KOSPI", kospi])
    print(f"🚀 기록 완료: {now} | KOSPI: {kospi}")

except Exception as e:
    print(f"🚨 최종 오류 발생: {e}")
