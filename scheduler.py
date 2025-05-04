import schedule
import time
import os
import subprocess
import logging
from datetime import datetime

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
    logging.info(f"실행 시간: {current_time}")
    
    # 스크립트 실행
    try:
        result = subprocess.run(['python', 'main.py', '--pages', '3', '--export'], 
                              cwd=project_dir,
                              capture_output=True, 
                              text=True, 
                              check=True)
        logging.info("명령어 출력:")
        logging.info(result.stdout)
        logging.info("모니터링 작업 완료")
    except subprocess.CalledProcessError as e:
        logging.error(f"모니터링 실행 중 오류 발생: {e}")
        logging.error(f"오류 출력: {e.stderr}")

if __name__ == "__main__":
    logging.info("네이버 검색 노출 모니터링 스케줄러가 시작되었습니다.")
    
    # 1시간마다 실행하도록 스케줄 설정
    schedule.every(1).hours.do(run_monitoring)
    
    # 시작할 때 한 번 즉시 실행 (선택 사항)
    logging.info("초기 모니터링 실행 중...")
    run_monitoring()
    
    logging.info("스케줄러가 1시간마다 모니터링을 실행하도록 설정되었습니다.")
    
    # 무한 루프로 스케줄러 실행
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 스케줄 확인
    except KeyboardInterrupt:
        logging.info("사용자에 의해 스케줄러가 중지되었습니다.")
    except Exception as e:
        logging.error(f"스케줄러 실행 중 오류 발생: {e}")
