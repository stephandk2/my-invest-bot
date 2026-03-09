import os
import json
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. GitHub Secrets에서 보안 값 불러오기
APP_KEY = os.environ.get("KIS_APP_KEY")
APP_SECRET = os.environ.get("KIS_APP_SECRET")
GSPREAD_JSON = os.environ.get("GSPREAD_JSON")

print(f"DEBUG: APP_KEY 존재 여부 = {APP_KEY is not None}")
print(f"DEBUG: APP_SECRET 존재 여부 = {APP_SECRET is not None}")
if APP_SECRET is None or APP_SECRET == "":
    print("⚠️ 경고: APP_SECRET 값이 비어있습니다! GitHub Secrets 설정을 확인하세요.")

def get_access_token():
    # 실전투자 URL (모의투자인 경우 openapiv.koreainvestment.com:9443 으로 수정 필요)
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    
    # 1. 헤더를 명시적으로 설정합니다.
    headers = {"Content-Type": "application/json"}
    
    # 2. 페이로드를 구성합니다.
    payload = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "secretkey": APP_SECRET
    }
    
    # 3. json= 옵션을 사용하여 자동으로 형식을 맞춥니다.
    res = requests.post(url, headers=headers, json=payload)
    res_data = res.json()
    
    if "access_token" not in res_data:
        print("❌ 한국투자증권 API 에러 발생!")
        print(f"상태 코드: {res.status_code}")
        print(f"에러 내용: {json.dumps(res_data, indent=2, ensure_ascii=False)}")
        
        # 만약 모의투자 키인데 실전 URL로 보냈을 경우에 대한 힌트
        if res.status_code == 403:
            print("💡 팁: '실전투자' 키가 맞는지, 혹은 '모의투자' URL을 써야 하는지 확인해 보세요.")
            
        raise Exception("토큰 발급 실패")
        
    return res_data["access_token"]

def get_market_data(token, code, div="U"):
    # 국내 지수(코스피: 0001, 코스닥: 1001) 조회
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price"
    headers = {"Content-Type":"application/json", "authorization":f"Bearer {token}", 
               "appkey":APP_KEY, "appsecret":APP_SECRET, "tr_id":"FHP31010000"}
    params = {"fid_cond_mrkt_div_code": div, "fid_input_iscd": code}
    res = requests.get(url, headers=headers, params=params)
    return res.json()['output']['bstp_nmix_prpr']

# 2. 구글 시트 연동
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# JSON 문자열을 딕셔너리로 변환하여 인증
creds_dict = json.loads(GSPREAD_JSON)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("2026_Invest_Ledger").sheet1

# 3. 데이터 수집 및 기록
try:
    token = get_access_token()
    kospi = get_market_data(token, "0001") # 코스피
    
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    sheet.append_row([now, "KOSPI", kospi])
    print(f"성공: {now} - KOSPI {kospi} 기록 완료")
except Exception as e:
    print(f"오류 발생: {e}")
