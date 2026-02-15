"""
네이버 키워드 노출 모니터링 스케줄러 - Google Sheets 기반
"""

import schedule
import time
import os
import sys
import subprocess
import logging
import traceback
import threading
from datetime import datetime
from src.config import OUTPUT_DIR, DATA_DIR

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
    send_email_report = None


def run_monitoring():
    """모니터링 스크립트 실행 (Google Sheets 기반)"""
    logging.info("=" * 60)
    logging.info("모니터링 작업 시작 (Google Sheets 버전)")
    logging.info("=" * 60)

    # 현재 시간 기록
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"실행 시간: {current_time}")

    # 디렉토리 확인
    for dir_path, dir_name in [(OUTPUT_DIR, "출력"), (DATA_DIR, "데이터")]:
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                logging.info(f"{dir_name} 디렉토리 생성됨: {dir_path}")
            except Exception as e:
                logging.error(f"{dir_name} 디렉토리 생성 실패: {str(e)}")

    # 모니터링 실행 (Google Sheets 기반 - 카테고리 옵션 없음)
    try:
        process = subprocess.Popen(
            ['python', '-u', os.path.join(SCRIPT_DIR, 'main.py')],
            cwd=SCRIPT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # 실시간으로 출력 읽기
        for line in process.stdout:
            line = line.rstrip()
            if line:
                logging.info(f"  {line}")

        process.wait()

        if process.returncode == 0:
            logging.info("모니터링 작업 완료")
        else:
            logging.error(f"모니터링 실행 종료 코드: {process.returncode}")

    except Exception as e:
        logging.error(f"모니터링 실행 중 예외 발생: {str(e)}")
        logging.error(traceback.format_exc())


def run_email_report():
    """이메일 보고서 전송"""
    logging.info("이메일 보고서 전송 작업 시작")

    if send_email_report is None:
        logging.error("email_reporter 모듈이 로드되지 않아 이메일을 전송할 수 없습니다.")
        return False

    try:
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
        logging.error(traceback.format_exc())
        return False


def email_scheduler_thread():
    """이메일 스케줄러를 별도 스레드에서 실행"""
    while True:
        schedule.run_pending()
        time.sleep(30)  # 30초마다 스케줄 확인


if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info(" 네이버 검색 노출 모니터링 스케줄러 (Google Sheets 버전)")
    logging.info("=" * 60)

    # 이메일 보고서 전송 스케줄 (매일 특정 시간에 전송)
    schedule.every().day.at("10:10").do(run_email_report)
    schedule.every().day.at("12:30").do(run_email_report)

    # 이메일 스케줄러를 별도 스레드에서 실행
    email_thread = threading.Thread(target=email_scheduler_thread, daemon=True)
    email_thread.start()

    logging.info("모니터링이 연속 실행 모드로 설정되었습니다. (검사 완료 후 즉시 재검사)")
    logging.info("매일 10:10, 12:30에 이메일 보고서를 전송하도록 설정되었습니다.")

    # 무한 루프로 연속 모니터링 실행
    try:
        while True:
            run_monitoring()
            logging.info("모니터링 작업 완료. 캐시/쿠키 초기화 후 다음 검사를 시작합니다...")
    except KeyboardInterrupt:
        logging.info("사용자에 의해 스케줄러가 중지되었습니다.")
    except Exception as e:
        logging.error(f"스케줄러 실행 중 오류 발생: {str(e)}")
        logging.error(traceback.format_exc())
