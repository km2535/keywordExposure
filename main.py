"""
네이버 키워드 노출 모니터링 도구 - DB 기반
"""

import os
import argparse
from src.scraper import NaverScraper
from src.monitor import KeywordMonitor
from src.db_client import DatabaseClient
from src.google_sheets import GoogleSheetsClient
from src.config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_TABLE,
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_SHEETS_ID, GOOGLE_SHEETS_GID,
    KEYWORD_LIST_SHEETS_ID, KEYWORD_LIST_SHEETS_GID
)
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

def main():
    logging.info("=" * 60)
    logging.info(" 네이버 키워드 노출 모니터링 (DB 버전)")
    logging.info("=" * 60)

    parser = argparse.ArgumentParser(description='네이버 검색 노출 모니터링 도구 (DB)')
    parser.add_argument('--check-deleted', action='store_true',
                        help='게시글 삭제 여부만 확인')
    args = parser.parse_args()

    # DB 클라이언트 초기화
    logging.info("\n DB 연결 중...")
    db_client = DatabaseClient(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, table=DB_TABLE
    )

    if not db_client.connect():
        logging.error("DB 연결 실패. 프로그램을 종료합니다.")
        return

    # ① 키워드순찰 시트 클라이언트
    logging.info("\n [1/2] 키워드순찰 시트 연결 중...")
    patrol_sheets_client = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=GOOGLE_SHEETS_ID,
        sheet_gid=GOOGLE_SHEETS_GID
    )
    if not patrol_sheets_client.connect():
        logging.warning("키워드순찰 시트 연결 실패 — 해당 시트 동기화를 건너뜁니다.")
        patrol_sheets_client = None

    # ② 키워드목록 시트 클라이언트
    logging.info("\n [2/2] 키워드목록 시트 연결 중...")
    keyword_list_sheets_client = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=KEYWORD_LIST_SHEETS_ID,
        sheet_gid=KEYWORD_LIST_SHEETS_GID
    )
    if not keyword_list_sheets_client.connect():
        logging.warning("키워드목록 시트 연결 실패 — 해당 시트 동기화를 건너뜁니다.")
        keyword_list_sheets_client = None

    # Scraper 초기화
    scraper = NaverScraper()

    # Monitor 초기화 (두 시트 클라이언트 모두 전달)
    monitor = KeywordMonitor(
        scraper, db_client,
        sheets_client=patrol_sheets_client,
        keyword_list_sheets_client=keyword_list_sheets_client
    )

    if args.check_deleted:
        logging.info("\n게시글 삭제 여부 확인 중...")
        monitor.check_deleted_posts()
        return

    # 모니터링 실행
    logging.info("\n키워드 모니터링 시작...")
    results = monitor.monitor_keywords()

    logging.info(f"\n모니터링 완료! (처리 {len(results)}건)")


if __name__ == "__main__":
    main()
