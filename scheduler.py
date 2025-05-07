import schedule
import time
import os
import sys
import subprocess
import logging
import traceback
from datetime import datetime
from src.config import DEFAULT_PAGES, SCHEDULER_INTERVAL, OUTPUT_DIR

# 현재 스크립트 디렉토리의 절대 경로
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(SCRIPT_DIR, 'monitoring_scheduler.log')),
        logging.StreamHandler()
    ]
)

# email_reporter 모듈을 확실히 로드하기 위해 시스템 경로에 현재 디렉토리 추가
sys.path.insert(0, SCRIPT_DIR)

# 이제 email_reporter를 임포트
try:
    from email_reporter import send_email_report
    logging.info("email_reporter 모듈을 성공적으로 로드했습니다.")
except ImportError as e:
    logging.error(f"email_reporter 모듈 로드 실패: {str(e)}")
    logging.error(f"시스템 경로: {sys.path}")
    sys.exit(1)

def run_monitoring():
    """모니터링 스크립트 실행"""
    logging.info("모니터링 작업 시작")
    
    # 현재 시간 기록
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_hour = datetime.now().hour
    logging.info(f"실행 시간: {current_time}")
    
    # 모니터링 디렉토리 확인
    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            logging.info(f"출력 디렉토리 생성됨: {OUTPUT_DIR}")
        except Exception as e:
            logging.error(f"출력 디렉토리 생성 실패: {str(e)}")
    
    # 모든 카테고리 실행
    try:
        result = subprocess.run(['python3', os.path.join(SCRIPT_DIR, 'main.py'), 
                                 '--pages', str(DEFAULT_PAGES), 
                                 '--all-categories'], 
                              cwd=SCRIPT_DIR,
                              capture_output=True, 
                              text=True, 
                              check=True)
        logging.info("명령어 출력:")
        logging.info(result.stdout)
        logging.info("모니터링 작업 완료")
        
        # 아침 7시일 경우 이메일 보고서 전송
        if current_hour == 7:
            run_email_report()
                
    except subprocess.CalledProcessError as e:
        logging.error(f"모니터링 실행 중 오류 발생: {e}")
        logging.error(f"오류 출력: {e.stderr}")

def run_email_report():
    """이메일 보고서만 전송하는 함수"""
    logging.info("이메일 보고서 전송 작업 시작")
    
    try:
        # 출력 디렉토리 존재 확인
        if not os.path.exists(OUTPUT_DIR):
            logging.error(f"출력 디렉토리가 없습니다: {OUTPUT_DIR}")
            return False
            
        # 결과 파일 존재 확인
        result_files_exist = False
        for category in ['cancer', 'diabetes', 'cream']:
            file_path = os.path.join(OUTPUT_DIR, f'latest_results_{category}.json')
            if os.path.exists(file_path):
                result_files_exist = True
                logging.info(f"결과 파일 확인됨: {file_path}")
            else:
                logging.warning(f"결과 파일 없음: {file_path}")
        
        if not result_files_exist:
            logging.error("어떤 결과 파일도 찾을 수 없습니다. 이메일 전송을 중단합니다.")
            return False
            
        # 이메일 전송 시도
        logging.info("이메일 전송 함수 호출 시작")
        email_sent = send_email_report()
        
        if email_sent:
            logging.info("이메일 보고서 전송 완료")
            return True
        else:
            logging.error("이메일 보고서 전송 실패")
            return False
    except Exception as e:
        logging.error(f"이메일 보고서 전송 중 예외 발생: {str(e)}")
        logging.error(traceback.format_exc())  # 스택 트레이스 로깅
        return False

if __name__ == "__main__":
    logging.info("네이버 검색 노출 모니터링 스케줄러가 시작되었습니다.")
    
    # 설정된 시간 간격마다 실행하도록 스케줄 설정
    schedule.every(SCHEDULER_INTERVAL).hours.do(run_monitoring)
    
    # 아침 7시에 이메일 보고서 전송 (독립적으로 실행)
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
        logging.error(f"스케줄러 실행 중 오류 발생: {str(e)}")
        logging.error(traceback.format_exc())  # 스택 트레이스 로깅