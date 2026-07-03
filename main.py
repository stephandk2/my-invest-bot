import os
import json
import requests
import gspread
from datetime import datetime
import pytz
import yfinance as yf
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import xml.etree.ElementTree as ET

# 환경 변수 로드
APP_KEY = os.environ.get("KIS_APP_KEY")
APP_SECRET = os.environ.get("KIS_APP_SECRET")
GSPREAD_JSON = os.environ.get("GSPREAD_JSON")
GMAIL_USER = os.environ.get("GMAIL_USER")          # 본인의 Gmail 주소
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD") # 구글 계정에서 발급받은 16자리 앱 비밀번호

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

def fetch_kis_stock(token, symbol):
    """한국투자증권 API: 국내 개별 주식 가격 조회 전용"""
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
        "fid_input_iscd": str(symbol).zfill(6)
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

def fetch_naver_blog_rss(blog_id, author_name):
    """네이버 블로그 RSS 피드 파싱 함수"""
    url = f"https://rss.blog.naver.com/{blog_id}"
    
    # 깃허브 액션 IP 차단을 막기 위해 일반 브라우저인 것처럼 User-Agent 위장
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code != 200:
            return f"❌ {author_name} 블로그 접근 실패 (Status: {res.status_code})"
            
        # XML 데이터 파싱
        root = ET.fromstring(res.text)
        
        # 최근 게시글 1개만 추출
        item = root.find('.//item')
        if item is not None:
            title = item.find('title').text
            link = item.find('link').text
            pub_date = item.find('pubDate').text
            
            return f"[{author_name}] {title}\n  - 링크: {link}\n  - 발행: {pub_date}"
        else:
            return f"⚠️ {author_name} 블로그에 최근 게시글이 없습니다."
            
    except Exception as e:
        return f"🚨 {author_name} 블로그 파싱 에러: {e}"

try:
    # 1. KIS 인증 및 시트 연결
    token = get_access_token()
    creds_dict = json.loads(GSPREAD_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    
    spreadsheet = client.open("2026_Invest_Ledger")
    config_sheet = spreadsheet.worksheet("Config")
    holdings_sheet = spreadsheet.get_worksheet(1)  
    
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
            if "FHPUP" in tr_id:
                val = fetch_kis_kospi(token, symbol)
            elif tr_id == "STOCK":
                val = fetch_kis_stock(token, symbol)
            else:
                val = fetch_yf_data(symbol)
                
            new_rows.append([now, name, val])
            print(f"✅ {name}: {val} 수집 완료")
        except Exception as e:
            print(f"❌ {name} 수집 실패: {e}")

    # 3-2. 네이버 블로그 전문가 인사이트 파싱
    blog_targets = [
        {"id": "worldforsale", "name": "에드몽당테스"},
        {"id": "hyy4467", "name": "황이영"},
        {"id": "ranto28", "name": "메르"}
    ]

    blog_news_dump = "\n\n=== EXPERT_BLOG_UPDATES ===\n"
    for blog in blog_targets:
        result = fetch_naver_blog_rss(blog["id"], blog["name"])
        blog_news_dump += result + "\n\n"

    # 4. 시트에 쓰지 않고, 규격화된 텍스트 이메일로 전송
    if new_rows:
        # 제미나이가 바로 파싱할 수 있는 텍스트 블록 조립
        email_body = "=== LEDGER_DATA_DUMP ===\n"
        email_body += f"Generated at: {now} KST\n\n"
        
        for idx, row in enumerate(new_rows):
            email_body += f"{idx + 1}. {row[1]} : {row[2]}\n"
            
        email_body += "\n========================="
        
        # 🎯 블로그 파싱 텍스트를 이메일 본문 하단에 병합
        email_body += blog_news_dump

        # SMTP 이메일 객체 생성
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = GMAIL_USER  # 자기 자신에게 발송
        msg['Subject'] = f"[Ledger_Sync] Morning Market & Asset Data Dumps"
        msg.attach(MIMEText(email_body, 'plain', 'utf-8'))

        # Gmail SSL 보안 서버 연동 후 발송
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_USER, GMAIL_PASSWORD)
                server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
            print(f"🚀 Gmail 전송 성공 (`[Ledger_Sync]` 패키지): {now}")
        except Exception as mail_err:
            print(f"❌ 이메일 전송 단계 오류: {mail_err}")
    else:
        print("⚠️ 수집된 데이터가 없어 이메일을 전송하지 않았습니다.")

except Exception as e:
    print(f"🚨 치명적 오류 발생: {e}")
