"""
네이버 키워드 노출 모니터링 도구 - Google Sheets 기반
"""

import os
import argparse
from src.scraper import NaverScraper
from src.monitor import KeywordMonitor
from src.reporter import Reporter
from src.google_sheets import GoogleSheetsClient
from src.config import (
    CONFIG_DIR, DATA_DIR, OUTPUT_DIR,
    GOOGLE_SHEETS_ID, GOOGLE_SHEETS_GID, GOOGLE_CREDENTIALS_PATH
)
import logging

def main():
    logging.info("=" * 60)
    logging.info(" 네이버 키워드 노출 모니터링 (Google Sheets 버전)")
    logging.info("=" * 60)

    parser = argparse.ArgumentParser(description='네이버 검색 노출 모니터링 도구 (Google Sheets)')
    parser.add_argument('--report', action='store_true',
                        help='현재 시트 상태 기준 보고서만 생성 (검색 안함)')
    parser.add_argument('--stats', action='store_true',
                        help='통계 정보만 출력')
    parser.add_argument('--export-csv', action='store_true',
                        help='미노출 키워드 CSV 내보내기')

    args = parser.parse_args()

    # 필요한 디렉토리 생성
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Google Sheets 인증 파일 확인
    if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
        logging.info(f"\n❌ 오류: Google 서비스 계정 인증 파일을 찾을 수 없습니다.")
        logging.info(f"   경로: {GOOGLE_CREDENTIALS_PATH}")
        logging.info("\n📋 설정 방법:")
        logging.info("   1. Google Cloud Console에서 서비스 계정 생성")
        logging.info("   2. JSON 키 파일 다운로드")
        logging.info(f"   3. {GOOGLE_CREDENTIALS_PATH} 경로에 저장")
        logging.info("   4. Google Sheets에서 해당 서비스 계정 이메일에 편집 권한 부여")
        return

    # Google Sheets 클라이언트 초기화
    logging.info("\n📊 Google Sheets 연결 중...")
    sheets_client = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=GOOGLE_SHEETS_ID,
        sheet_gid=GOOGLE_SHEETS_GID
    )

    if not sheets_client.connect():
        logging.info("❌ Google Sheets 연결 실패. 프로그램을 종료합니다.")
        return

    # Reporter 초기화
    reporter = Reporter(sheets_client)

    # 보고서만 생성 모드
    if args.report:
        logging.info("\n📄 보고서 생성 모드...")
        reporter.logging.info_report()
        return

    # 통계만 출력 모드
    if args.stats:
        reporter.logging.info_statistics()
        return

    # CSV 내보내기 모드
    if args.export_csv:
        reporter.export_csv_for_unexposed()
        return

    # 모니터링 실행
    logging.info("\n🔍 키워드 모니터링 시작...")

    # Scraper 초기화
    scraper = NaverScraper()

    # Monitor 초기화
    monitor = KeywordMonitor(scraper, sheets_client)

    # 모니터링 실행
    results = monitor.monitor_keywords()

    # 결과 보고서 출력
    logging.info("\n" + "=" * 60)
    reporter.logging.info_report()

    # 통계 출력
    reporter.logging.info_statistics()

    logging.info("\n✅ 모니터링 완료!")


if __name__ == "__main__":
    main()
