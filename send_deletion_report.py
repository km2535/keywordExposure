"""
최근 일주일 발행 키워드 중 미노출 키워드 이메일 발송 스크립트
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from src.google_sheets import GoogleSheetsClient
from src.config import (
    GOOGLE_SHEETS_ID,
    GOOGLE_SHEETS_GID,
    GOOGLE_CREDENTIALS_PATH,
    EMAIL_SENDER,
    EMAIL_PASSWORD,
    EMAIL_RECIPIENTS
)


def get_unexposed_keywords_last_week(sheets_client):
    """
    최근 일주일 발행된 키워드 중 미노출 키워드 목록 가져오기 (삭제 여부 포함)
    """
    all_data = sheets_client.get_all_data()
    today = datetime.now()
    one_week_ago = today - timedelta(days=7)

    unexposed_keywords = []

    for row in all_data:
        exposure_status = row.get('노출', '').strip()

        # 미노출 키워드만 처리 (X)
        if exposure_status.upper() != 'X':
            continue

        keyword = row.get('키워드', '').strip()
        if not keyword:
            continue

        # 발행시간 파싱
        publish_time_str = row.get('발행시간', '').strip()
        if not publish_time_str:
            continue  # 발행시간이 없으면 제외

        publish_date = None
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y']:
            try:
                publish_date = datetime.strptime(publish_time_str, fmt)
                break
            except ValueError:
                continue

        # 최근 일주일 이내 발행된 것만 포함
        if not publish_date or publish_date < one_week_ago:
            continue

        cafe = row.get('카페', '').strip()
        post_url = row.get('url', '').strip()
        patrol_time_str = row.get('순찰시간', '').strip()
        deletion_status = row.get('삭제', '').strip()

        unexposed_keywords.append({
            'keyword': keyword,
            'cafe': cafe,
            'url': post_url,
            'publish_time': publish_time_str,
            'publish_date': publish_date,
            'patrol_time': patrol_time_str,
            'deletion_status': deletion_status
        })

    # 발행시간 기준 정렬 (최신순)
    unexposed_keywords.sort(key=lambda x: x['publish_date'], reverse=True)

    return unexposed_keywords


def create_email_html(unexposed_keywords):
    """
    미노출 키워드 이메일 HTML 생성
    """
    today = datetime.now().strftime('%Y-%m-%d')
    one_week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Malgun Gothic', Arial, sans-serif; }}
            h2 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 13px; }}
            th {{ background-color: #e67e22; color: white; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            tr:hover {{ background-color: #f1f1f1; }}
            .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .deleted {{ color: #e74c3c; font-weight: bold; }}
            .unexposed {{ color: #e67e22; font-weight: bold; }}
            a {{ color: #3498db; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h2>⚠️ 미노출 키워드 현황 리포트</h2>
        <div class="summary">
            <p><strong>발행 기간:</strong> {one_week_ago} ~ {today}</p>
            <p><strong>미노출 키워드:</strong> <span class="unexposed">{len(unexposed_keywords)}개</span></p>
        </div>
    """

    if unexposed_keywords:
        html += """
        <table>
            <tr>
                <th>No</th>
                <th>카페</th>
                <th>키워드</th>
                <th>발행시간</th>
                <th>순찰시간</th>
                <th>삭제여부</th>
                <th>URL</th>
            </tr>
        """

        for idx, item in enumerate(unexposed_keywords, 1):
            url_display = item['url'][:40] + '...' if len(item['url']) > 40 else item['url']
            deletion_display = item['deletion_status'] if item['deletion_status'] else '-'
            deletion_class = 'class="deleted"' if item['deletion_status'] else ''
            html += f"""
            <tr>
                <td>{idx}</td>
                <td>{item['cafe']}</td>
                <td>{item['keyword']}</td>
                <td>{item['publish_time']}</td>
                <td>{item['patrol_time']}</td>
                <td {deletion_class}>{deletion_display}</td>
                <td><a href="{item['url']}">{url_display}</a></td>
            </tr>
            """

        html += "</table>"
    else:
        html += "<p>✅ 최근 일주일 발행 키워드 중 미노출 키워드가 없습니다.</p>"

    html += """
        <br>
        <p style="color: #888; font-size: 11px;">이 리포트는 자동으로 생성되었습니다.</p>
    </body>
    </html>
    """

    return html


def send_email(subject, html_content, recipients):
    """이메일 발송"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = ', '.join(recipients)

    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipients, msg.as_string())
        print(f"✅ 이메일이 성공적으로 발송되었습니다: {recipients}")
        return True
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")
        return False


def main():
    """메인 실행 함수"""
    print("=" * 60)
    print(" 최근 일주일 미노출 키워드 리포트 생성")
    print("=" * 60)

    # 1. Google Sheets 연결
    print("\n1. Google Sheets 연결 중...")
    sheets_client = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=GOOGLE_SHEETS_ID,
        sheet_gid=GOOGLE_SHEETS_GID
    )

    if not sheets_client.connect():
        print("Google Sheets 연결 실패!")
        return

    # 2. 미노출 키워드 조회 (최근 일주일 발행분)
    print("\n2. 최근 일주일 발행 중 미노출 키워드 조회 중...")
    unexposed_keywords = get_unexposed_keywords_last_week(sheets_client)
    print(f"   미노출 키워드: {len(unexposed_keywords)}개")

    # 3. 이메일 내용 생성
    print("\n3. 이메일 내용 생성 중...")
    html_content = create_email_html(unexposed_keywords)

    # 4. 이메일 발송
    today = datetime.now().strftime('%Y-%m-%d')
    subject = f"[키워드 모니터링] 미노출 현황 리포트 ({today})"

    print(f"\n4. 이메일 발송 중... (수신자: {EMAIL_RECIPIENTS})")
    send_email(subject, html_content, EMAIL_RECIPIENTS)

    print("\n" + "=" * 60)
    print(" 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
