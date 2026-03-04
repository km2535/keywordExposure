"""
단일 키워드 테스트 스크립트 - '당화혈색소 검사기'
DB에서 해당 키워드 행만 가져와서 모니터링 결과 확인
"""
import logging
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

TARGET_KEYWORD = '암요양병원실비'

def main():
    db_client = DatabaseClient(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, table=DB_TABLE
    )
    if not db_client.connect():
        print("DB 연결 실패")
        return

    # DB에서 해당 키워드 행만 필터링
    all_items = db_client.get_keywords_for_monitoring()
    items = [i for i in all_items if i['keyword'] == TARGET_KEYWORD]

    if not items:
        print(f"'{TARGET_KEYWORD}' 키워드를 DB에서 찾을 수 없습니다.")
        return

    print(f"\n=== DB 데이터 ({len(items)}행) ===")
    for item in items:
        print(f"  row={item['row']} | url={item['target_url'] or '(없음)'} | "
              f"is_deleted={item['is_deleted']} | is_exposed={item['current_status']}")

    # 모니터링 실행
    scraper = NaverScraper()
    scraper.reset_driver()

    soup = scraper.get_search_results(TARGET_KEYWORD, page=1)
    if not soup:
        print("검색 결과 가져오기 실패")
        return

    search_urls = scraper.extract_main_urls(soup)
    popular_urls = scraper.extract_popular_post_urls(soup)

    # HTML 저장
    with open('debug_search.html', 'w', encoding='utf-8') as f:
        f.write(str(soup))
    print("HTML 저장: debug_search.html")

    # 디버그: 실제 HTML에서 data-heatmap-target 속성값 종류 출력
    heatmap_values = set()
    for a in soup.find_all('a', attrs={'data-heatmap-target': True}):
        heatmap_values.add(a.get('data-heatmap-target'))
    print(f"\n=== [디버그] data-heatmap-target 값 종류: {heatmap_values} ===")

    # 디버그: cafe/blog URL이 있는 a 태그 샘플
    naver_links = [(a.get('href', ''), dict(a.attrs)) for a in soup.find_all('a', href=True)
                   if 'cafe.naver.com' in a.get('href','') or 'blog.naver.com' in a.get('href','')]
    print(f"=== [디버그] cafe/blog 링크 {len(naver_links)}개 발견, 샘플 3개 ===")
    for href, attrs in naver_links[:3]:
        relevant = {k:v for k,v in attrs.items() if k in ('href','data-heatmap-target','class')}
        print(f"  {relevant}")

    print(f"\n=== 검색 결과 URL ({len(search_urls)}개) ===")
    for idx, u in enumerate(search_urls, 1):
        print(f"  [{idx}] {u}")

    print(f"\n=== 인기글 URL ({len(popular_urls)}개) ===")
    for u in popular_urls:
        print(f"  {u}")

    monitor = KeywordMonitor(scraper, db_client)

    # url_to_keyword 매핑 (교차키워드용)
    url_to_keyword = {}
    for item in all_items:
        norm = monitor.normalize_url(item.get('target_url', ''))
        if norm:
            url_to_keyword[norm] = item['keyword']

    # 교차키워드 계산
    cross_keywords = []
    seen_kws = set()
    for idx, search_url in enumerate(search_urls, start=1):
        norm = monitor.normalize_url(search_url)
        mapped_kw = url_to_keyword.get(norm)
        if mapped_kw and mapped_kw != TARGET_KEYWORD and mapped_kw not in seen_kws:
            seen_kws.add(mapped_kw)
            cross_keywords.append(f"{mapped_kw}({idx})")

    print(f"\n=== 교차키워드: {cross_keywords} ===")

    print(f"\n=== 각 행 처리 결과 ===")
    batch_updates = []
    for item in items:
        target_url = item['target_url']
        row = item['row']

        if not target_url:
            update = {
                'row': row,
                'cross_keywords': cross_keywords,
                'popular_status': 'O' if popular_urls else 'X',
            }
            print(f"  row={row} | URL없음 | 교차={cross_keywords} | 인기글={'O' if popular_urls else 'X'}")
            batch_updates.append(update)
            continue

        if item.get('is_deleted') == 'O':
            update = {
                'row': row,
                'url': target_url,
                'cross_keywords': cross_keywords,
                'popular_status': 'O' if popular_urls else 'X',
            }
            print(f"  row={row} | 이미삭제 | {target_url}")
            batch_updates.append(update)
            continue

        is_deleted, err_msg = scraper.check_post_deleted(target_url)
        if is_deleted is None:
            if 'cafe.naver.com' not in (target_url or ''):
                is_deleted = False
            else:
                print(f"  row={row} | 삭제확인실패({err_msg}) | {target_url}")
                continue

        popular_status = "O" if popular_urls else "X"
        if is_deleted:
            exposure_status, deletion_status, rank = "X", "O", None
        else:
            deletion_status = "X"
            rank = monitor.find_url_position(target_url, search_urls)
            exposure_status = "O" if rank else "X"

        print(f"  row={row} | 삭제={deletion_status} | 노출={exposure_status} | 순위={rank} | {target_url}")
        batch_updates.append({
            'row': row,
            'url': target_url,
            'exposure_status': exposure_status,
            'deletion_status': deletion_status,
            'cross_keywords': cross_keywords,
            'rank': rank,
            'popular_status': popular_status,
        })

    # DB 업데이트
    print(f"\n총 {len(batch_updates)}건 DB 업데이트 예정")
    db_client.batch_update_monitoring_results(batch_updates)
    print("DB 업데이트 완료!")

    scraper.close_driver()

    # 키워드순찰 시트 동기화
    print("\n키워드순찰 시트 동기화 중...")
    patrol_sheets = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=GOOGLE_SHEETS_ID,
        sheet_gid=GOOGLE_SHEETS_GID
    )
    if patrol_sheets.connect():
        headers, rows = db_client.get_all_patrol_logs()
        if rows:
            patrol_sheets.sync_patrol_logs(headers, rows)
            print(f"키워드순찰 시트 동기화 완료 ({len(rows)}행)")
        else:
            print("키워드순찰 시트 동기화 대상 없음")
    else:
        print("키워드순찰 시트 연결 실패")

    # 키워드목록 시트 동기화
    print("\n키워드목록 시트 동기화 중...")
    keyword_list_sheets = GoogleSheetsClient(
        credentials_path=GOOGLE_CREDENTIALS_PATH,
        spreadsheet_id=KEYWORD_LIST_SHEETS_ID,
        sheet_gid=KEYWORD_LIST_SHEETS_GID
    )
    if keyword_list_sheets.connect():
        kl_headers, kl_rows = db_client.get_keyword_list_from_view()
        if kl_rows:
            keyword_list_sheets.sync_patrol_logs(kl_headers, kl_rows)
            print(f"키워드목록 시트 동기화 완료 ({len(kl_rows)}행)")
        else:
            print("키워드목록 시트 동기화 대상 없음")
    else:
        print("키워드목록 시트 연결 실패")


if __name__ == "__main__":
    main()
