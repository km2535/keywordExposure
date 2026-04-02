"""
블로그 포스트 모니터링 모듈 - DB 기반
KeywordMonitor와 유사하지만 삭제 확인 로직 제외
"""

from typing import List, Optional
import logging
from tqdm import tqdm


class BlogMonitor:
    """DB 기반 블로그 포스트 모니터링 클래스"""

    def __init__(self, scraper, db_client, sheets_client=None):
        """
        초기화

        Args:
            scraper: NaverScraper 인스턴스
            db_client: DatabaseClient 인스턴스
            sheets_client: GoogleSheetsClient 인스턴스 (블로그순찰 시트 동기화용, 선택)
        """
        self.scraper = scraper
        self.db_client = db_client
        self.sheets_client = sheets_client

    def normalize_url(self, url: str) -> str:
        """URL 정규화 — NaverScraper.normalize_url 위임 (단일 공통 로직)"""
        return self.scraper.normalize_url(url)

    def find_url_position(self, url: str, search_urls: List[str]) -> Optional[int]:
        """
        타겟 URL의 검색 결과 내 순위 찾기 (1-based)
        찾지 못하면 None 반환
        """
        target = self.normalize_url(url)
        for idx, search_url in enumerate(search_urls, start=1):
            if self.normalize_url(search_url) == target:
                return idx
        return None

    def monitor_blog_posts(self, products=None):
        """
        DB 기반 블로그 포스트 모니터링
        같은 키워드는 한 번만 검색하되, 각 URL의 노출 여부는 개별적으로 확인합니다.
        검색은 requests 우선, 실패 시 Selenium 폴백으로 진행합니다.
        순찰 성공/실패 여부와 관계없이 완료 후 반드시 블로그 시트를 동기화합니다.

        Args:
            products: 필터링할 제품 목록 (예: ['cancer', 'diabetes']). None이면 전체.
        """
        blog_posts_data = self.db_client.get_blog_posts_for_monitoring(products=products)
        if not blog_posts_data:
            logging.info("모니터링할 블로그 포스트가 없습니다.")
            self._sync_blog_sheets()
            return []

        # 1. 키워드별로 데이터 그룹화 (검색 횟수 최소화 목적)
        keyword_groups = {}
        for item in blog_posts_data:
            kw = item['keyword']
            if kw not in keyword_groups:
                keyword_groups[kw] = []
            keyword_groups[kw].append(item)

        # 교차노출 감지용: 정규화된 URL → 키워드 역매핑
        url_to_keyword = {}
        for item in blog_posts_data:
            norm = self.normalize_url(item.get('target_url', ''))
            if norm:
                url_to_keyword[norm] = item['keyword']

        batch_updates = []

        try:
            # 2. 키워드별 루프 (requests 우선, 실패 시 Selenium 폴백은 get_search_results 내부에서 처리)
            for keyword, items in tqdm(keyword_groups.items(), desc="블로그 키워드별 모니터링 진행 중"):
                try:
                    # 해당 키워드의 네이버 검색 결과는 한 번만 가져옴
                    # get_search_results: requests 시도 → 실패 시 Selenium 자동 전환
                    soup = self.scraper.get_search_results(keyword, page=1)
                    if not soup:
                        logging.warning(f"키워드 '{keyword}' 검색 결과 가져오기 실패 (requests+Selenium 모두 실패), 건너뜀")
                        continue
                    search_urls = self.scraper.extract_main_urls(soup)
                    popular_urls = self.scraper.extract_popular_post_urls(soup)
                except Exception as e:
                    logging.error(f"키워드 '{keyword}' 검색 중 오류 발생, 건너뜀: {e}")
                    continue

                # 교차노출 감지: 이 키워드의 검색 결과에 다른 키워드의 URL이 있는지 확인
                cross_keywords = []
                seen_kws = set()
                for idx, search_url in enumerate(search_urls, start=1):
                    norm = self.normalize_url(search_url)
                    mapped_kw = url_to_keyword.get(norm)
                    if mapped_kw and mapped_kw != keyword and mapped_kw not in seen_kws:
                        seen_kws.add(mapped_kw)
                        cross_keywords.append(f"{mapped_kw}({idx})")
                if cross_keywords:
                    logging.info(f"교차노출 감지 - 키워드 '{keyword}': {cross_keywords}")

                # 3. 같은 키워드 내의 각 URL(행)들을 개별 검사
                for item in items:
                    target_url = item['target_url']
                    row = item['row']

                    # 이미 삭제된 포스트는 순찰시간 업데이트 없이 건너뜀
                    if item.get('is_deleted'):
                        continue

                    if not target_url:
                        batch_updates.append({
                            'row': row,
                            'cross_keywords': cross_keywords,
                        })
                        continue

                    try:
                        rank = self.find_url_position(target_url, search_urls)
                        is_exposed = rank is not None
                        exposure_status = "O" if is_exposed else "X"

                        # 인기글 여부
                        norm_target = self.normalize_url(target_url)
                        popular_status = "O" if norm_target in popular_urls else "X"

                        # 삭제 확인 (미노출 시에만 — Selenium alert 방식)
                        deletion_status = None
                        if not is_exposed:
                            is_deleted, _ = self.scraper.check_post_deleted(target_url)
                            if is_deleted is not None:
                                deletion_status = 'O' if is_deleted else 'X'

                        # 결과 데이터 구성
                        update = {
                            'row': row,
                            'url': target_url,
                            'exposure_status': exposure_status,
                            'popular_status': popular_status,
                            'cross_keywords': cross_keywords,
                            'rank': rank,
                        }
                        if deletion_status is not None:
                            update['deletion_status'] = deletion_status

                        batch_updates.append(update)
                    except Exception as e:
                        logging.error(f"블로그 행 {row} 처리 중 오류 발생, 건너뜀: {e}")
                        continue

            # 4. DB 일괄 업데이트
            if batch_updates:
                self.db_client.batch_update_blog_results(batch_updates)

        finally:
            # 드라이버 종료 (Selenium이 사용된 경우)
            self.scraper.close_driver()

            # 5. Google Sheets 동기화 — 순찰 성공/실패 무관하게 반드시 실행
            self._sync_blog_sheets()

        return batch_updates

    def _sync_blog_sheets(self):
        """블로그순찰 시트 Google Sheets 동기화 (항상 실행)"""
        if not self.sheets_client:
            logging.warning("sheets_client 미설정 — Google Sheets 동기화 생략")
            return
        try:
            logging.info("Google Sheets 동기화 시작 (블로그순찰 시트)...")
            headers, rows = self.db_client.get_all_blog_patrol_logs()
            if rows:
                self.sheets_client.sync_patrol_logs(headers, rows)
                logging.info("블로그 시트 Google Sheets 동기화 완료")
            else:
                logging.warning("블로그 Google Sheets 동기화 대상 데이터 없음")
        except Exception as e:
            logging.error(f"블로그 시트 Google Sheets 동기화 중 오류: {e}")
