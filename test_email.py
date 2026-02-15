#!/usr/bin/env python3
"""
이메일 보고서 전송 테스트 스크립트
네이버 검색 모니터링 결과 이메일 발송을 테스트합니다.
"""

import argparse
import sys
from datetime import datetime
from email_reporter import send_email_report
import logging

def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description='네이버 검색 모니터링 이메일 보고서 테스트')
    parser.add_argument('--recipients', type=str, help='테스트 수신자 이메일 (쉼표로 구분)')
    
    args = parser.parse_args()
    
    logging.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서 테스트 시작")
    
    # 테스트 이메일 전송
    result = send_email_report()
    
    if result:
        logging.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서 전송 성공!")
        sys.exit(0)
    else:
        logging.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 이메일 보고서 전송 실패.")
        sys.exit(1)

if __name__ == "__main__":
    main()
