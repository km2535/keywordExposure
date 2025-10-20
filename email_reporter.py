import os
import json
import smtplib
import requests
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from src.config import (
    OUTPUT_DIR, 
    CATEGORIES, 
    CATEGORY_NAMES, 
    EMAIL_SENDER, 
    EMAIL_PASSWORD, 
    EMAIL_RECIPIENTS
)

# ----------------------------------------------------
# A. 키워드 검색량 조회 및 동적 비교 로직 (Period 계산 로직 수정)
# ----------------------------------------------------

# 트렌드를 조회할 키워드 목록
KEYWORDS = [
    "발효황칠뿌리진액",
    "근당대사 식품"
]

def format_api_date_str(dt: datetime) -> str:
    """
    datetime 객체를 검색량 API가 요구하는 형식으로 변환합니다.
    """
    day_mapping = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}
    day_en = day_mapping[dt.weekday()]
    
    date_part = dt.strftime(f"{day_en} %b %d %Y")
    time_tz_part = "13:12:52 GMT+0900 (한국 표준시)"
    
    return f"{date_part} {time_tz_part}"

def calculate_comparison_periods():
    """
    오늘의 요일에 따라 비교 기준을 동적으로 설정합니다.
    - 월요일: 지지난주(7일) vs 지난주(7일)
    - 화~일: 지난주(7일 전체) vs 이번주(시작일~어제)
    """
    now = datetime.now()
    today_weekday = now.weekday() # 월=0, 화=1, ..., 일=6
    report_end_date = now.date() - timedelta(days=1) # 보고서 마감일 (항상 어제)
    
    # 한국식 요일명
    days_kr = ['월', '화', '수', '목', '금', '토', '일']
    today_kr = days_kr[today_weekday]
    
    period_1_start = None
    period_1_end = None
    period_2_start = None
    period_2_end = None
    
    period_1_name = ""
    period_2_name = ""
    api_start_date = None
    api_end_date = None

    if today_weekday == 0: # 월요일인 경우: 지지난주 vs 지난주 (월~일 전체 비교)
        
        # Period 2: 지난주 (월~일)
        last_sunday = report_end_date 
        last_monday = last_sunday - timedelta(days=6)
        
        # Period 1: 지지난주 (월~일)
        prev_sunday = last_monday - timedelta(days=1)
        prev_monday = prev_sunday - timedelta(days=6)
        
        period_1_start = prev_monday
        period_1_end = prev_sunday
        period_2_start = last_monday
        period_2_end = last_sunday
        
        period_1_name = "지지난주"
        period_2_name = "지난주"
        
        # API 호출 기간은 지지난주 월요일부터 지난주 일요일까지 총 14일
        api_start_date = prev_monday
        api_end_date = last_sunday
        
    else: # 화요일~일요일인 경우: 지난주(7일 전체) vs 이번주(시작일~어제)
        
        # 이번 주의 시작일 (월요일)
        this_week_start = now.date() - timedelta(days=today_weekday)
        
        # Period 2: 이번 주 (시작일 ~ 어제)
        period_2_start = this_week_start
        period_2_end = report_end_date # 어제
        
        # Period 1: 지난주 (월요일 ~ 일요일)
        period_1_start = this_week_start - timedelta(days=7) # 지난주 월요일
        period_1_end = period_1_start + timedelta(days=6) # 지난주 일요일 <--- **수정: 7일 전체로 고정**

        period_1_name = "지난주"
        period_2_name = "이번주"
        
        # API 호출 기간은 Period 1 시작일(지지난주 월요일)부터 Period 2 종료일(어제)까지 (최대 14일)
        api_start_date = period_1_start
        api_end_date = report_end_date 
        # (API는 이 기간의 모든 데이터를 가져와야 Period 1의 7일 전체를 확보할 수 있음)

    return {
        'api_start_date': api_start_date,
        'api_end_date': api_end_date,
        'period_1_start': period_1_start.strftime('%Y-%m-%d'),
        'period_1_end': period_1_end.strftime('%Y-%m-%d'),
        'period_2_start': period_2_start.strftime('%Y-%m-%d'),
        'period_2_end': period_2_end.strftime('%Y-%m-%d'),
        'period_1_name': period_1_name,
        'period_2_name': period_2_name,
        'today_kr': today_kr
    }


def get_keyword_search_summary():
    """
    2주간의 검색량 데이터를 가져와 각 주차별로 일별 데이터를 분리하여 반환합니다.
    """
    periods = calculate_comparison_periods()
    
    all_keyword_comparison_data = {}
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 키워드 트렌드 조회 시작 ({periods['api_start_date']} ~ {periods['api_end_date']})")

    api_start_str = format_api_date_str(datetime.combine(periods['api_start_date'], datetime.min.time()))
    api_end_str = format_api_date_str(datetime.combine(periods['api_end_date'], datetime.min.time()))
    
    # 주차별 시작/종료 날짜를 datetime 객체로 변환하여 비교에 사용
    period_1_end_dt = datetime.strptime(periods['period_1_end'], '%Y-%m-%d').date()

    for keyword in KEYWORDS:
        encoded_keyword = quote(keyword)
        BASE_URL = f"https://pandarank.net/api/keywords/{encoded_keyword}/graph"

        params = {
            "startDate": api_start_str,
            "endDate": api_end_str,
            "period": "date"
        }

        try:
            response = requests.get(BASE_URL, params=params, timeout=10)
            response.raise_for_status() 
            data = response.json()
            
            if data.get('status', {}).get('code') == 200 and 'items' in data:
                items = data['items']
                
                if items and isinstance(items[0], dict) and 'keys' in items[0] and 'values' in items[0]:
                    keys = items[0]['keys'] # 날짜
                    values = items[0]['values'] # 트렌드 값
                    
                    if not values:
                         print(f"  ⚠️ 키워드: {keyword} - 데이터는 있으나 값이 비어있음.")
                         continue
                        
                    # 2주 데이터를 분리하여 저장
                    period_1_data = [] # 이전 주차 데이터
                    period_2_data = [] # 현재 주차 데이터
                    
                    for date_str, value in zip(keys, values):
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        day_of_week_kr = ['월', '화', '수', '목', '금', '토', '일'][date_obj.weekday()]
                        
                        daily_entry = {
                            'date': date_str,
                            'day': day_of_week_kr,
                            'value': value
                        }
                        
                        # 기간 1의 종료일(지난주 일요일)과 비교하여 분리
                        if date_obj.date() <= period_1_end_dt:
                            period_1_data.append(daily_entry)
                        else:
                            period_2_data.append(daily_entry)
                    
                    # 최종 데이터 구조에 저장
                    all_keyword_comparison_data[keyword] = {
                        'period_1': period_1_data,
                        'period_2': period_2_data,
                    }
                    print(f"  ✅ 키워드: {keyword} - 2주 데이터({len(period_1_data)}일/{len(period_2_data)}일) 분리 완료.")

                else:
                    print(f"  ⚠️ 키워드: {keyword} - 데이터 구조 오류.")
            else:
                print(f"  ❌ 키워드: {keyword} - API 응답 실패: Code {data.get('status', {}).get('code', 'N/A')}")

        except requests.exceptions.RequestException as e:
            print(f"  ❌ 키워드: {keyword} - 네트워크/API 오류 발생: {e}")
            continue

    # 기간 정보와 비교 데이터를 함께 반환
    return all_keyword_comparison_data, periods


# ----------------------------------------------------
# B. 기존 함수 (노출 결과 로드)
# ----------------------------------------------------

def load_latest_results():
    """모든 카테고리의 최신 노출 결과를 로드"""
    all_results = {}
    
    for category in CATEGORIES:
        json_path = os.path.join(OUTPUT_DIR, f'latest_results_{category}.json') 
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    all_results[category] = json.load(f)
            except Exception as e:
                print(f"{category} 결과 로드 중 오류: {str(e)}")
                all_results[category] = None
        else:
            print(f"경고: {json_path} 파일이 없습니다.")
            all_results[category] = None
            
    return all_results

# ----------------------------------------------------
# C. HTML 보고서 생성 함수 (변함 없음: 유연성 유지)
# ----------------------------------------------------

def generate_html_report(all_results, comparison_data, periods):
    """요약된 HTML 형식의 이메일 보고서 생성"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # HTML 헤더 및 스타일 (생략 - 기존과 동일)
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #333366; }}
            h2 {{ color: #666699; margin-top: 30px; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
            .summary-card {{ 
                border: 1px solid #ddd; 
                border-radius: 8px; 
                padding: 15px; 
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            .card-header {{ 
                font-size: 18px; 
                font-weight: bold; 
                margin-bottom: 10px;
                padding-bottom: 5px;
                border-bottom: 1px solid #eee;
            }}
            .stat-container {{
                display: flex;
                justify-content: space-between;
                flex-wrap: wrap;
            }}
            .stat-box {{
                flex: 1;
                min-width: 120px;
                padding: 10px;
                margin: 5px;
                border-radius: 5px;
                text-align: center;
            }}
            .success-box {{ background-color: rgba(0, 128, 0, 0.1); border: 1px solid rgba(0, 128, 0, 0.3); }}
            .warning-box {{ background-color: rgba(255, 165, 0, 0.1); border: 1px solid rgba(255, 165, 0, 0.3); }}
            .danger-box {{ background-color: rgba(255, 0, 0, 0.1); border: 1px solid rgba(255, 0, 0, 0.3); }}
            .number {{ font-size: 24px; font-weight: bold; margin: 5px 0; }}
            .label {{ font-size: 14px; color: #666; }}
            .success {{ color: green; }}
            .warning {{ color: orange; }}
            .danger {{ color: red; }}
            .footer {{ margin-top: 30px; font-size: 12px; color: #666; border-top: 1px solid #eee; padding-top: 10px; }}
            .comparison-table {{ /* 새 비교 테이블 스타일 */
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }}
            .comparison-table th, .comparison-table td {{
                border: 1px solid #ddd;
                padding: 8px 10px;
                text-align: center;
                font-size: 14px;
                line-height: 1.3;
            }}
            .comparison-table th {{
                background-color: #f2f2f2;
                font-weight: bold;
            }}
            .comparison-table .week-header {{ 
                background-color: #f8f8f8; 
                font-weight: bold; 
                width: 15%; /* 주차 헤더 너비 고정 */
            }}
            .trend-value {{ font-weight: bold; font-size: 16px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>네이버 검색 트렌드 및 노출 일일 요약 리포트</h1>
            <p>생성 시간: {now}</p>
    """
    
    # ----------------------------------------------------
    # 1. 키워드 검색량 트렌드 비교 섹션 (최상단)
    # ----------------------------------------------------
    
    if comparison_data:
        html += f"""
        <div style="margin-top: 20px;">
            <h2>📈 주간 키워드 검색량 변화 비교 ({periods['today_kr']}요일 기준)</h2>
        """
        
        # 키워드별 테이블 생성
        for keyword, data in comparison_data.items():
            period_1_data = data['period_1']
            period_2_data = data['period_2']
            
            # 요일은 '월'부터 시작하여 7개
            days_kr = ['월', '화', '수', '목', '금', '토', '일']
            
            html += f"""
            <div class="summary-card" style="margin-top: 20px;">
                <div class="card-header">키워드: {keyword}</div>
                
                <table class="comparison-table">
                    <thead>
                        <tr>
                            <th>주차 / 요일</th>
                            <th>{days_kr[0]}</th>
                            <th>{days_kr[1]}</th>
                            <th>{days_kr[2]}</th>
                            <th>{days_kr[3]}</th>
                            <th>{days_kr[4]}</th>
                            <th>{days_kr[5]}</th>
                            <th>{days_kr[6]}</th>
                        </tr>
                    </thead>
                    <tbody>
                    """
            
            # --- 기간 1 (이전 주차) ---
            # 1. 기간 1 날짜 Row
            date_row = f'<td class="week-header">{periods["period_1_name"]}<br>({periods["period_1_start"].split("-")[1]}.{periods["period_1_start"].split("-")[2]}~{periods["period_1_end"].split("-")[1]}.{periods["period_1_end"].split("-")[2]})</td>'
            # 2. 기간 1 검색량 Row
            value_row = '<td class="week-header">검색량</td>'
            
            # Period 1은 7일치 전체를 보여줍니다.
            for i in range(7):
                if i < len(period_1_data):
                    period_1_day_data = period_1_data[i]
                    date_row += f'<td>{period_1_day_data["date"].split("-")[1]}.{period_1_day_data["date"].split("-")[2]}({period_1_day_data["day"]})</td>'
                    value_row += f'<td><span class="trend-value">{period_1_day_data["value"]}</span></td>'
                else:
                    # 데이터가 7일 미만일 경우 (예외 상황 대비)
                    date_row += '<td>---</td>'
                    value_row += '<td>---</td>'
            
            html += f'<tr>{date_row}</tr>'
            html += f'<tr>{value_row}</tr>'

            # --- 기간 2 (현재 주차) ---
            # 1. 기간 2 날짜 Row
            date_row_last = f'<td class="week-header">{periods["period_2_name"]}<br>({periods["period_2_start"].split("-")[1]}.{periods["period_2_start"].split("-")[2]}~{periods["period_2_end"].split("-")[1]}.{periods["period_2_end"].split("-")[2]})</td>'
            # 2. 기간 2 검색량 Row
            value_row_last = '<td class="week-header">검색량</td>'
            
            # Period 2는 현재 진행 중인 데이터(어제까지)만 표시하고 나머지는 하이픈 처리
            for i in range(7): 
                style = ""
                
                if i < len(period_2_data): # <--- 데이터가 존재하는 경우 (과거)
                    period_2_day_data = period_2_data[i]
                    date_row_last += f'<td>{period_2_day_data["date"].split("-")[1]}.{period_2_day_data["date"].split("-")[2]}({period_2_day_data["day"]})</td>'
                    
                    # 값 비교를 통해 스타일 적용 (Period 1의 해당 요일 데이터가 있을 때만 비교)
                    if i < len(period_1_data):
                        period_1_value = period_1_data[i]["value"]
                        period_2_value = period_2_day_data["value"]
                        
                        if period_2_value > period_1_value:
                            style = 'style="background-color: #e6ffe6;"' # 성장
                        elif period_2_value < period_1_value:
                            style = 'style="background-color: #ffe6e6;"' # 하락

                    value_row_last += f'<td {style}><span class="trend-value">{period_2_day_data["value"]}</span></td>'
                else: # <--- 데이터가 존재하지 않는 경우 (미래)
                    date_row_last += '<td>-</td>' 
                    value_row_last += '<td><span class="trend-value">-</span></td>' 
                    
            html += f'<tr>{date_row_last}</tr>'
            html += f'<tr>{value_row_last}</tr>'
            
            html += """
                    </tbody>
                </table>
            </div>
            """
            
        html += "</div>"
        
    # ----------------------------------------------------
    # 2. 네이버 검색 노출 모니터링 섹션 (이하 기존 로직 유지)
    # ----------------------------------------------------
    
    html += f"""
        <hr style="margin-top: 40px; border: 0; border-top: 1px solid #eee;">
        <div style="margin-top: 40px;">
            <h2>🔍 네이버 검색 노출 모니터링 결과</h2>
        </div>
    """
    
    # ... (기존 노출 통계 계산 및 HTML 생성 로직 유지) ...
    total_exposed = 0
    total_not_exposed = 0
    total_no_url = 0
    
    for category, results in all_results.items():
        if results is None:
            continue
            
        category_display = CATEGORY_NAMES.get(category, category.upper())
        exposed_keywords = []
        not_exposed_keywords = []
        no_url_keywords = []
        
        for keyword_result in results.get("results", []):
            keyword = keyword_result.get("keyword", "")
            urls = keyword_result.get("urls", [])
            
            if not urls:
                no_url_keywords.append(keyword)
                continue
            exposed_count = sum(1 for url in urls if url.get("is_exposed", False))
            
            if exposed_count > 0:
                exposed_keywords.append(keyword)
            else:
                not_exposed_keywords.append(keyword)
        
        total_with_url = total_exposed + total_not_exposed
        exposure_rate = 0 if total_with_url == 0 else round(len(exposed_keywords) / total_with_url * 100)
        
        total_exposed += len(exposed_keywords)
        total_not_exposed += len(not_exposed_keywords)
        total_no_url += len(no_url_keywords)
        
        html += f"""
        <div class="summary-card">
            <div class="card-header">{category_display} ({category.upper()})</div>
            <p>최종 업데이트: {results.get('timestamp', '알 수 없음')}</p>
            
            <div class="stat-container">
                <div class="stat-box success-box">
                    <div class="number success">{len(exposed_keywords)}</div>
                    <div class="label">노출된 키워드</div>
                </div>
                <div class="stat-box danger-box">
                    <div class="number danger">{len(not_exposed_keywords)}</div>
                    <div class="label">노출되지 않은 키워드</div>
                </div>
                <div class="stat-box warning-box">
                    <div class="number warning">{len(no_url_keywords)}</div>
                    <div class="label">발행하지 않은 키워드</div>
                </div>
            </div>
            
            <p><strong>노출률:</strong> <span class="{'success' if exposure_rate >= 70 else 'warning' if exposure_rate >= 30 else 'danger'}">{exposure_rate}%</span> (발행한 키워드 중)</p>
            
        </div>
        """
    
    # 전체 요약 카드 (기존 로직 유지)
    total_with_url = total_exposed + total_not_exposed
    total_keywords = total_with_url + total_no_url
    total_exposure_rate = 0 if total_with_url == 0 else round(total_exposed / total_with_url * 100)
    url_creation_rate = 0 if total_keywords == 0 else round(total_with_url / total_keywords * 100, 2)
    
    html += f"""
        <div class="summary-card">
            <div class="card-header">전체 요약</div>
            
            <div class="stat-container">
                <div class="stat-box success-box">
                    <div class="number success">{total_exposed}</div>
                    <div class="label">노출된 키워드</div>
                </div>
                <div class="stat-box danger-box">
                    <div class="number danger">{total_not_exposed}</div>
                    <div class="label">노출되지 않은 키워드</div>
                </div>
                <div class="stat-box warning-box">
                    <div class="number warning">{total_no_url}</div>
                    <div class="label">발행하지 않은 키워드</div>
                </div>
            </div>
            
            <p><strong>전체 노출률:</strong> <span class="{'success' if total_exposure_rate >= 70 else 'warning' if total_exposure_rate >= 30 else 'danger'}">{total_exposure_rate}%</span> (발행한 키워드 중)</p>
            <p><strong>발행률:</strong> <span class="{'success' if url_creation_rate >= 70 else 'warning' if url_creation_rate >= 30 else 'danger'}">{url_creation_rate}%</span> (전체 키워드 중)</p>
        </div>
    """
    
    # 푸터 (기존 로직 유지)
    html += """
            <div class="footer">
                <p>이 이메일은 자동으로 생성되었습니다. 문의사항이 있으시면 관리자에게 연락하세요.</p>
                <p>※ 상세 정보는 <a href='https://minsweb.shop'>minsweb.shop</a>에서 확인하실 수 있습니다.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

# ----------------------------------------------------
# D. 이메일 전송 함수
# ----------------------------------------------------

def send_email_report():
    """이메일 보고서 전송"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서 생성 중...")
    
    try:
        # 현재 날짜를 이메일 제목에 추가
        today_date = datetime.now().strftime("%Y-%m-%d")
        email_subject = f"네이버 검색 트렌드 및 노출 일일 리포트 ({today_date})"
        
        # 1. 키워드 검색량 2주 비교 데이터 생성 (동적 비교 로직 적용)
        comparison_data, periods = get_keyword_search_summary()
        
        # 2. 최신 노출 결과 로드
        all_results = load_latest_results()
        
        # 3. HTML 보고서 생성
        html_content = generate_html_report(all_results, comparison_data, periods)
        
        # 이메일 구성
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = ", ".join(EMAIL_RECIPIENTS)
        msg['Subject'] = email_subject
        
        # HTML 콘텐츠 추가
        msg.attach(MIMEText(html_content, 'html'))
        
        # SMTP 서버 연결 및 이메일 전송
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서가 성공적으로 전송되었습니다.")
        return True
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 전송 중 오류 발생: {str(e)}")
        return False