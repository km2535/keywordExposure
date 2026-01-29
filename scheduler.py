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
from datetime import datetime
from src.config import SCHEDULER_INTERVAL, OUTPUT_DIR, DATA_DIR

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
        result = subprocess.run(
            ['python3', os.path.join(SCRIPT_DIR, 'main.py')],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        logging.info("명령어 출력:")
        for line in result.stdout.split('\n'):
            if line.strip():
                logging.info(f"  {line}")
        logging.info("모니터링 작업 완료")

    except subprocess.CalledProcessError as e:
        logging.error(f"모니터링 실행 중 오류 발생: {e.cmd}")
        logging.error(f"오류 출력: {e.stderr}")
    except Exception as e:
        logging.error(f"모니터링 실행 중 일반 예외 발생: {str(e)}")
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


if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info(" 네이버 검색 노출 모니터링 스케줄러 (Google Sheets 버전)")
    logging.info("=" * 60)

    # 설정된 시간 간격마다 실행하도록 스케줄 설정
    schedule.every(SCHEDULER_INTERVAL).hours.do(run_monitoring)

    # 이메일 보고서 전송 스케줄
    schedule.every().day.at("10:10").do(run_email_report)
    schedule.every().day.at("12:30").do(run_email_report)

    # 시작할 때 한 번 즉시 실행
    logging.info("초기 모니터링 실행 중...")
    run_monitoring()

    logging.info(f"스케줄러가 {SCHEDULER_INTERVAL}시간마다 모니터링을 실행하도록 설정되었습니다.")
    logging.info("매일 10:10, 12:30에 이메일 보고서를 전송하도록 설정되었습니다.")

    # 무한 루프로 스케줄러 실행
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 스케줄 확인
    except KeyboardInterrupt:
        logging.info("사용자에 의해 스케줄러가 중지되었습니다.")
    except Exception as e:
        logging.error(f"스케줄러 실행 중 오류 발생: {str(e)}")
        logging.error(traceback.format_exc())
