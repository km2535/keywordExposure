import schedule
import time
import os
import subprocess
import logging
from datetime import datetime
from src.config import DEFAULT_PAGES, SCHEDULER_INTERVAL
from email_reporter import send_email_report  # 새로 추가된 임포트

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitoring_scheduler.log'),
        logging.StreamHandler()
    ]
)

def run_monitoring():
    """모니터링 스크립트 실행"""
    logging.info("모니터링 작업 시작")
    
    # 현재 파일의 디렉토리를 프로젝트 경로로 사용
    project_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 현재 시간 기록
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_hour = datetime.now().hour
    logging.info(f"실행 시간: {current_time}")
    
    # 모든 카테고리 실행
    try:
        result = subprocess.run(['python3', 'main.py', '--pages', str(DEFAULT_PAGES), '--all-categories'], 
                              cwd=project_dir,
                              capture_output=True, 
                              text=True, 
                              check=True)
        logging.info("명령어 출력:")
        logging.info(result.stdout)
        logging.info("모니터링 작업 완료")
        
        # 아침 7시일 경우 이메일 보고서 전송
        if current_hour == 7:
            logging.info("아침 7시 이메일 보고서 전송 시작")
            email_sent = send_email_report()
            if email_sent:
                logging.info("이메일 보고서 전송 완료")
            else:
                logging.error("이메일 보고서 전송 실패")
                
    except subprocess.CalledProcessError as e:
        logging.error(f"모니터링 실행 중 오류 발생: {e}")
        logging.error(f"오류 출력: {e.stderr}")

def run_email_report():
    """이메일 보고서만 전송하는 함수"""
    logging.info("이메일 보고서 전송 작업 시작")
    
    try:
        email_sent = send_email_report()
        if email_sent:
            logging.info("이메일 보고서 전송 완료")
        else:
            logging.error("이메일 보고서 전송 실패")
    except Exception as e:
        logging.error(f"이메일 보고서 전송 중 오류 발생: {e}")

if __name__ == "__main__":
    logging.info("네이버 검색 노출 모니터링 스케줄러가 시작되었습니다.")
    
    # 설정된 시간 간격마다 실행하도록 스케줄 설정
    schedule.every(SCHEDULER_INTERVAL).hours.do(run_monitoring)
    
    # 아침 7시에 이메일 보고서 전송
    schedule.every().day.at("07:00").do(run_email_report)
    
    # 시작할 때 한 번 즉시 실행 (선택 사항)
    logging.info("초기 모니터링 실행 중...")
    run_monitoring()
    
    logging.info(f"스케줄러가 {SCHEDULER_INTERVAL}시간마다 모니터링을 실행하도록 설정되었습니다.")
    logging.info("매일 아침 7시에 이메일 보고서를 전송하도록 설정되었습니다.")
    
    # 무한 루프로 스케줄러 실행
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 스케줄 확인
    except KeyboardInterrupt:
        logging.info("사용자에 의해 스케줄러가 중지되었습니다.")
    except Exception as e:
        logging.error(f"스케줄러 실행 중 오류 발생: {e}")