import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import schedule
import time
from src.config import (
    OUTPUT_DIR, 
    CATEGORIES, 
    CATEGORY_NAMES, 
    EMAIL_SENDER, 
    EMAIL_PASSWORD, 
    EMAIL_RECIPIENTS
)

def load_latest_results():
    """모든 카테고리의 최신 결과를 로드"""
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

def generate_html_report(all_results):
    """요약된 HTML 형식의 이메일 보고서 생성"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # HTML 헤더 및 스타일
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
            .detail-toggle {{ 
                background-color: #f8f8f8; 
                border: none; 
                padding: 8px 15px; 
                margin-top: 10px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                color: #666;
            }}
            .detail-toggle:hover {{ background-color: #ebebeb; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>네이버 검색 노출 모니터링 일일 요약 리포트</h1>
            <p>생성 시간: {now}</p>
    """
    
    # 전체 통계를 위한 변수
    total_exposed = 0
    total_not_exposed = 0
    total_no_url = 0
    
    # 카테고리별 요약 카드 생성
    for category, results in all_results.items():
        if results is None:
            continue
            
        category_display = CATEGORY_NAMES.get(category, category.upper())
        
        # 결과 분석
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
            total_count = len(urls)
            
            if exposed_count == total_count and total_count > 0:
                exposed_keywords.append(keyword)
            else:
                not_exposed_keywords.append(keyword)
        
        # 노출률 계산
        total_with_url = len(exposed_keywords) + len(not_exposed_keywords)
        exposure_rate = 0 if total_with_url == 0 else round(len(exposed_keywords) / total_with_url * 100)
        
        # 전체 통계 업데이트
        total_exposed += len(exposed_keywords)
        total_not_exposed += len(not_exposed_keywords)
        total_no_url += len(no_url_keywords)
        
        # 카드 시작
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
    
    # 전체 요약 카드
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
    
    # 푸터
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

def send_email_report():
    """이메일 보고서 전송"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서 생성 중...")
    
    try:
        # 현재 날짜를 이메일 제목에 추가
        today_date = datetime.now().strftime("%Y-%m-%d")
        email_subject = f"네이버 검색 노출 모니터링 일일 리포트 ({today_date})"
        
        # 최신 결과 로드
        all_results = load_latest_results()
        
        # HTML 보고서 생성
        html_content = generate_html_report(all_results)
        
        # 이메일 구성
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = ", ".join(EMAIL_RECIPIENTS)
        msg['Subject'] = email_subject  # 날짜가 포함된 제목 사용
        
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