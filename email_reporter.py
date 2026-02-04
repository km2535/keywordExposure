import os
import json
import smtplib
import requests
import csv
from urllib.parse import quote
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timedelta
from src.config import (
    EMAIL_SENDER,
    EMAIL_PASSWORD,
    EMAIL_RECIPIENTS,
    GOOGLE_SHEETS_ID,
    GOOGLE_SHEETS_GID,
    GOOGLE_CREDENTIALS_PATH
)
from src.reporter import Reporter # Reporter 클래스 임포트
from src.google_sheets import GoogleSheetsClient
import logging
# ----------------------------------------------------
# A. 키워드 검색량 조회 및 동적 비교 로직 (변함 없음)
# ----------------------------------------------------
# 트렌드를 조회할 키워드 목록
KEYWORDS = [
    "명인황근",
    "발효황칠뿌리진액",
    "근당대사 식품",
    "호르모닉스 크림"
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
        period_1_end = period_1_start + timedelta(days=6) # 지난주 일요일 

        period_1_name = "지난주"
        period_2_name = "이번주"
        
        # API 호출 기간은 Period 1 시작일(지지난주 월요일)부터 Period 2 종료일(어제)까지 (최대 14일)
        api_start_date = period_1_start
        api_end_date = report_end_date 

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
    (기존 로직 유지)
    """
    periods = calculate_comparison_periods()
    
    all_keyword_comparison_data = {}
    
    logging.info(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 키워드 트렌드 조회 시작 ({periods['api_start_date']} ~ {periods['api_end_date']})")

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
                         logging.info(f"  ⚠️ 키워드: {keyword} - 데이터는 있으나 값이 비어있음.")
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
                    logging.info(f"  ✅ 키워드: {keyword} - 2주 데이터({len(period_1_data)}일/{len(period_2_data)}일) 분리 완료.")

                else:
                    logging.info(f"  ⚠️ 키워드: {keyword} - 데이터 구조 오류.")
            else:
                logging.info(f"  ❌ 키워드: {keyword} - API 응답 실패: Code {data.get('status', {}).get('code', 'N/A')}")

        except requests.exceptions.RequestException as e:
            logging.info(f"  ❌ 키워드: {keyword} - 네트워크/API 오류 발생: {e}")
            continue

    # 기간 정보와 비교 데이터를 함께 반환
    return all_keyword_comparison_data, periods


# ----------------------------------------------------
# B. 노출 결과 로드 및 요약
# ----------------------------------------------------

def filter_recent_week_data(summary):
    """
    최근 일주일에 발행된 키워드만 필터링

    Args:
        summary: Reporter.generate_summary()의 반환값

    Returns:
        필터링된 summary
    """
    if not summary:
        return None

    one_week_ago = datetime.now() - timedelta(days=7)

    def is_recent_week(item):
        """발행시간이 최근 일주일 이내인지 확인"""
        publish_time = item.get('publish_time', '').strip()
        if not publish_time:
            return False

        # 다양한 날짜 형식 시도
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y']:
            try:
                publish_date = datetime.strptime(publish_time, fmt)
                return publish_date >= one_week_ago
            except ValueError:
                continue
        return False

    # 각 카테고리별로 필터링
    filtered_summary = {
        'timestamp': summary['timestamp'],
        'exposed': [item for item in summary['exposed'] if is_recent_week(item)],
        'not_exposed': [item for item in summary['not_exposed'] if is_recent_week(item)],
        'no_url': [item for item in summary['no_url'] if is_recent_week(item)]
    }

    # 총 개수 재계산
    filtered_summary['total'] = (
        len(filtered_summary['exposed']) +
        len(filtered_summary['not_exposed']) +
        len(filtered_summary['no_url'])
    )

    return filtered_summary


def get_all_reports(sheets_client):
    """Google Sheets에서 데이터를 가져와 요약 및 미노출 키워드 리스트 반환"""
    try:
        reporter = Reporter(sheets_client)
        summary = reporter.generate_summary()

        # 최근 일주일 데이터만 필터링
        filtered_summary = filter_recent_week_data(summary)

        # CSV 파일 생성 (미노출 키워드가 있을 경우)
        csv_path = None
        if filtered_summary and filtered_summary["not_exposed"]:
            # 필터링된 데이터로 CSV 생성을 위해 임시로 Reporter를 사용
            # 하지만 Reporter.export_csv_for_unexposed()는 전체 데이터를 사용하므로
            # 직접 CSV를 생성해야 함
            csv_path = export_filtered_csv(filtered_summary["not_exposed"])

        return filtered_summary, csv_path

    except Exception as e:
        logging.info(f"경고: 보고서 생성 중 오류 발생: {str(e)}")
        import traceback
        traceback.logging.info_exc()
        return None, None


def export_filtered_csv(not_exposed_list):
    """필터링된 미노출 키워드를 CSV로 저장"""
    if not not_exposed_list:
        return None

    from src.config import OUTPUT_DIR

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_filename = 'unexposed_keywords_recent_week.csv'
    csv_path = os.path.join(OUTPUT_DIR, csv_filename)

    header = ["키워드", "상태", "작성글 URL", "발행시간", "순찰시간"]
    data_rows = []

    for item in not_exposed_list:
        row = [
            item['keyword'],
            item['status'],
            item.get('post_url', ''),
            item.get('publish_time', ''),
            item.get('patrol_time', '')
        ]
        data_rows.append(row)

    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(data_rows)

    logging.info(f"최근 일주일 미노출 키워드 CSV가 {csv_path}에 저장되었습니다.")
    return csv_path

# ----------------------------------------------------
# C. HTML 보고서 생성 함수 (개선)
# ----------------------------------------------------

def generate_html_report(summary, comparison_data, periods):
    """요약된 HTML 형식의 이메일 보고서 생성"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # HTML 스타일
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
            .comparison-table {{
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
                width: 15%;
            }}
            .trend-value {{ font-weight: bold; font-size: 16px; }}
            .detail-table th, .detail-table td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #eee; }}
            .detail-table th {{ width: 30%; background-color: #fafafa; }}
            .critical {{ color: #CC0000; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>네이버 검색 트렌드 및 노출 일일 요약 리포트</h1>
            <p style="font-style: italic; color: #777;">
                키워드 노출 상태는 마케팅 성과의 핵심 지표입니다.<br>
                **모든 URL이 미노출된 키워드**에 대한 집중적인 분석이 필요합니다.
            </p>
            <p>생성 시간: {now}</p>
    """

    # ----------------------------------------------------
    # 1. 키워드 검색량 트렌드 비교 섹션
    # ----------------------------------------------------

    if comparison_data:
        html += f"""
        <div style="margin-top: 20px;">
            <h2>📈 주간 키워드 검색량 변화 비교 ({periods['today_kr']}요일 기준)</h2>
        """

        for keyword, data in comparison_data.items():
            period_1_data = data['period_1']
            period_2_data = data['period_2']
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
            date_row = f'<td class="week-header">{periods["period_1_name"]}<br>({periods["period_1_start"].split("-")[1]}.{periods["period_1_start"].split("-")[2]}~{periods["period_1_end"].split("-")[1]}.{periods["period_1_end"].split("-")[2]})</td>'
            value_row = '<td class="week-header">검색량</td>'
            for i in range(7):
                if i < len(period_1_data):
                    period_1_day_data = period_1_data[i]
                    date_row += f'<td>{period_1_day_data["date"].split("-")[1]}.{period_1_day_data["date"].split("-")[2]}({period_1_day_data["day"]})</td>'
                    value_row += f'<td><span class="trend-value">{period_1_day_data["value"]}</span></td>'
                else:
                    date_row += '<td>---</td>'
                    value_row += '<td>---</td>'
            html += f'<tr>{date_row}</tr>'
            html += f'<tr>{value_row}</tr>'

            # --- 기간 2 (현재 주차) ---
            date_row_last = f'<td class="week-header">{periods["period_2_name"]}<br>({periods["period_2_start"].split("-")[1]}.{periods["period_2_start"].split("-")[2]}~{periods["period_2_end"].split("-")[1]}.{periods["period_2_end"].split("-")[2]})</td>'
            value_row_last = '<td class="week-header">검색량</td>'
            for i in range(7):
                style = ""
                if i < len(period_2_data):
                    period_2_day_data = period_2_data[i]
                    date_row_last += f'<td>{period_2_day_data["date"].split("-")[1]}.{period_2_day_data["date"].split("-")[2]}({period_2_day_data["day"]})</td>'
                    if i < len(period_1_data):
                        period_1_value = period_1_data[i]["value"]
                        period_2_value = period_2_day_data["value"]
                        if period_2_value > period_1_value:
                            style = 'style="background-color: #e6ffe6;"'
                        elif period_2_value < period_1_value:
                            style = 'style="background-color: #ffe6e6;"'
                    value_row_last += f'<td {style}><span class="trend-value">{period_2_day_data["value"]}</span></td>'
                else:
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
    # 2. 노출 요약 섹션
    # ----------------------------------------------------

    if summary:
        
        # ----------------------------------------------------
        # 3. 미노출 키워드 상세 리스트
        # ----------------------------------------------------
        if summary['not_exposed']:
            html += f"""
        <div style="margin-top: 30px;">
            <h2>🚨 미노출 키워드 상세 목록 ({len(summary['not_exposed'])}개)</h2>
            <div class="summary-card">
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                        <tr style="background-color: #f44336; color: white;">
                            <th style="border: 1px solid #ddd; padding: 10px; text-align: center;">No</th>
                            <th style="border: 1px solid #ddd; padding: 10px; text-align: left;">키워드</th>
                            <th style="border: 1px solid #ddd; padding: 10px; text-align: center;">발행시간</th>
                            <th style="border: 1px solid #ddd; padding: 10px; text-align: center;">순찰시간</th>
                            <th style="border: 1px solid #ddd; padding: 10px; text-align: left;">URL</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for idx, item in enumerate(summary['not_exposed'], 1):
                keyword = item.get('keyword', '')
                publish_time = item.get('publish_time', '')
                patrol_time = item.get('patrol_time', '')
                post_url = item.get('post_url', '')

                # URL을 짧게 표시
                url_display = post_url[:50] + '...' if len(post_url) > 50 else post_url

                # 행 배경색 (짝수/홀수)
                row_bg = '#f9f9f9' if idx % 2 == 0 else 'white'

                html += f"""
                        <tr style="background-color: {row_bg};">
                            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
                            <td style="border: 1px solid #ddd; padding: 8px; font-weight: bold;">{keyword}</td>
                            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{publish_time}</td>
                            <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{patrol_time}</td>
                            <td style="border: 1px solid #ddd; padding: 8px;"><a href="{post_url}" style="color: #3498db; text-decoration: none;">{url_display}</a></td>
                        </tr>
                """

            html += """
                    </tbody>
                </table>
            </div>
        </div>
            """

    # HTML 종료
    html += """
        </div>
        <div class="footer">
            <p>이 보고서는 자동으로 생성되었습니다.</p>
        </div>
    </body>
    </html>
    """

    return html

# ----------------------------------------------------
# D. 이메일 전송 함수 (첨부 파일 처리 추가) - 변함 없음
# ----------------------------------------------------

def send_email_report():
    """이메일 보고서 전송"""
    logging.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서 생성 중...")

    try:
        # Google Sheets 클라이언트 초기화
        logging.info("📊 Google Sheets 연결 중...")
        sheets_client = GoogleSheetsClient(
            credentials_path=GOOGLE_CREDENTIALS_PATH,
            spreadsheet_id=GOOGLE_SHEETS_ID,
            sheet_gid=GOOGLE_SHEETS_GID
        )

        if not sheets_client.connect():
            logging.info("❌ Google Sheets 연결 실패")
            return False

        # 현재 날짜를 이메일 제목에 추가
        today_date = datetime.now().strftime("%Y-%m-%d")
        email_subject = f"[네이버 검색 트렌드 및 노출 일일 리포트] {today_date}"

        # 1. 키워드 검색량 2주 비교 데이터 생성
        comparison_data, periods = get_keyword_search_summary()

        # 2. 최신 노출 결과 로드 및 요약 생성
        summary, csv_path = get_all_reports(sheets_client)

        # 3. HTML 보고서 생성
        html_content = generate_html_report(summary, comparison_data, periods)

        # 이메일 구성
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = ", ".join(EMAIL_RECIPIENTS)
        msg['Subject'] = email_subject

        # HTML 콘텐츠 추가
        msg.attach(MIMEText(html_content, 'html'))

        # CSV 파일 첨부 (미노출 키워드가 있을 경우)
        if csv_path and os.path.exists(csv_path):
            with open(csv_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename={os.path.basename(csv_path)}'
                )
                msg.attach(part)
            logging.info(f"📎 CSV 파일 첨부: {os.path.basename(csv_path)}")

        # SMTP 서버 연결 및 이메일 전송
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)

        logging.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서가 성공적으로 전송되었습니다.")
        return True
    except Exception as e:
        logging.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 전송 중 오류 발생: {str(e)}")
        import traceback
        traceback.logging.info_exc()
        return False


if __name__ == "__main__":
    send_email_report()