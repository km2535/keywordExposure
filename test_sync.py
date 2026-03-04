"""
시트 동기화 테스트 스크립트
- 모니터링 없이 DB → Google Sheets 동기화만 실행
"""

import logging
from src.db_client import DatabaseClient
from src.google_sheets import GoogleSheetsClient
from src.config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_TABLE,
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_SHEETS_ID, GOOGLE_SHEETS_GID,
    KEYWORD_LIST_SHEETS_ID, KEYWORD_LIST_SHEETS_GID
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

def main():
    # DB 연결
    logging.info("DB 연결 중...")
    db = DatabaseClient(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, table=DB_TABLE
    )
    if not db.connect():
        logging.error("DB 연결 실패")
        return

    # ① 키워드순찰 시트 동기화
    logging.info("=" * 50)
    logging.info("[1/2] 키워드순찰 시트 동기화 시작")
    patrol_client = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=GOOGLE_SHEETS_ID,
        sheet_gid=GOOGLE_SHEETS_GID
    )
    if patrol_client.connect():
        headers, rows = db.get_all_patrol_logs()
        logging.info(f"  patrol_logs 로드: {len(rows)}행")
        if rows:
            patrol_client.sync_patrol_logs(headers, rows)
            logging.info("  키워드순찰 시트 동기화 완료 ✓")
        else:
            logging.warning("  동기화할 데이터 없음")
    else:
        logging.error("  키워드순찰 시트 연결 실패")

    # ② 키워드목록 시트 동기화
    logging.info("=" * 50)
    logging.info("[2/2] 키워드목록 시트 동기화 시작")
    keyword_list_client = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=KEYWORD_LIST_SHEETS_ID,
        sheet_gid=KEYWORD_LIST_SHEETS_GID
    )
    if keyword_list_client.connect():
        kl_headers, kl_rows = db.get_keyword_list_from_view()
        logging.info(f"  keyword_list_view 로드: {len(kl_rows)}행")
        if kl_rows:
            keyword_list_client.sync_patrol_logs(kl_headers, kl_rows)
            logging.info("  키워드목록 시트 동기화 완료 ✓")
        else:
            logging.warning("  동기화할 데이터 없음")
    else:
        logging.error("  키워드목록 시트 연결 실패")

    logging.info("=" * 50)
    logging.info("테스트 완료")


if __name__ == "__main__":
    main()
