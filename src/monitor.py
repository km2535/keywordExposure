"""
키워드 모니터링 모듈 - DB 기반
"""

from datetime import datetime
from tqdm import tqdm
from urllib.parse import urlparse
from typing import List, Dict, Optional
import logging

class KeywordMonitor:
    """DB 기반 키워드 모니터링 클래스"""

    def __init__(self, scraper, db_client, sheets_client=None):
        """
        초기화

        Args:
            scraper: NaverScraper 인스턴스
            db_client: DatabaseClient 인스턴스
            sheets_client: GoogleSheetsClient 인스턴스 (키워드순찰 시트 동기화용, 선택)
        """
        self.scraper = scraper
        self.db_client = db_client
        self.sheets_client = sheets_client

    def normalize_url(self, url: str) -> str:
        """URL 정규화 — NaverScraper.normalize_url 위임 (단일 공통 로직)"""
        return self.scraper.normalize_url(url)

    def check_url_in_results(self, url: str, search_urls: List[str]) -> bool:
        """
        타겟 URL이 검색 결과에 포함되어 있는지 확인
        """
        target = self.normalize_url(url)
        for search_url in search_urls:
            if self.normalize_url(search_url) == target:
                return True
        return False

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

    def get_cafe_id_from_url(self, url: str) -> Optional[str]:
        """URL에서 카페 ID 추출"""
        if not url or 'cafe.naver.com' not in url:
            return None

        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        if path_parts:
            return path_parts[0]
        return None

    def monitor_keywords(self):
        """
        DB 기반 키워드 모니터링
        같은 키워드는 한 번만 검색하되, 각 URL의 삭제 여부는 개별적으로 확인합니다.
        매 실행 시 캐시와 쿠키를 초기화하여 깨끗한 상태에서 시작합니다.
        """
        # 캐시/쿠키 초기화: 이전 드라이버가 남아있으면 완전히 리셋
        self.scraper.reset_driver()
        print("캐시/쿠키 초기화 완료 - 깨끗한 상태에서 모니터링을 시작합니다.")

        keywords_data = self.db_client.get_keywords_for_monitoring()
        if not keywords_data:
            return []

        # 1. 키워드별로 데이터 그룹화 (검색 횟수 최소화 목적)
        # 교차노출 검사를 위해 삭제된 키워드도 검색 대상에 포함
        keyword_groups = {}
        for item in keywords_data:
            kw = item['keyword']
            if kw not in keyword_groups:
                keyword_groups[kw] = []
            # 모든 항목을 개별 처리 목록에 추가 (삭제·URL없음 여부 무관, 교차노출 기록 대상)
            keyword_groups[kw].append(item)

        # 교차노출 감지용: 정규화된 URL → 키워드 역매핑
        # 삭제된 항목도 포함하여 모든 키워드의 URL을 수집
        url_to_keyword = {}
        for item in keywords_data:
            norm = self.normalize_url(item.get('target_url', ''))
            if norm:
                url_to_keyword[norm] = item['keyword']

        batch_updates = []

        # 2. 키워드별 루프
        for keyword, items in tqdm(keyword_groups.items(), desc="키워드별 모니터링 진행 중"):
            try:
                # 해당 키워드의 네이버 검색 결과는 한 번만 가져옴
                # data-heatmap-target=".link" 인 메인 노출 URL만 사용
                soup = self.scraper.get_search_results(keyword, page=1)
                if not soup:
                    logging.warning(f"키워드 '{keyword}' 검색 결과 가져오기 실패, 건너뜀")
                    continue
                search_urls = self.scraper.extract_main_urls(soup)
                popular_urls = self.scraper.extract_popular_post_urls(soup)
            except Exception as e:
                logging.error(f"키워드 '{keyword}' 검색 중 오류 발생, 건너뜀: {e}")
                continue

            # 교차노출 감지: 이 키워드의 검색 결과에 다른 키워드의 URL이 있는지 확인
            # 교차키워드는 "키워드(순위)" 형식으로 저장
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

                if not target_url:
                    # URL 없는 항목: 인기글 섹션 존재 여부만 기록
                    batch_updates.append({
                        'row': row,
                        'cross_keywords': cross_keywords,
                        'popular_status': 'O' if popular_urls else 'X',
                    })
                    continue

                if item.get('is_deleted') == 'O':
                    # 이미 삭제된 항목: 인기글은 검색 결과 기준으로 업데이트
                    popular_status = "O" if popular_urls else "X"
                    batch_updates.append({
                        'row': row,
                        'url': target_url,
                        'cross_keywords': cross_keywords,
                        'popular_status': popular_status,
                    })
                    continue

                try:
                    # [개별 확인] 게시글 삭제 여부를 URL마다 각각 확인
                    is_deleted, err_msg = self.scraper.check_post_deleted(target_url)

                    if is_deleted is None:
                        # 삭제 확인 자체가 실패한 경우 — 이 행은 건너뜀
                        logging.warning(f"삭제 확인 실패, 건너뜀 (행 {row}): {target_url} / {err_msg}")
                        continue

                    popular_status = "O" if popular_urls else "X"
                    if is_deleted:
                        # 삭제된 경우: 노출 X, 삭제 O
                        exposure_status = "X"
                        deletion_status = "O"
                        rank = None
                    else:
                        # 살아있는 경우: 검색 결과에서 순위(위치) 확인
                        deletion_status = "X"
                        rank = self.find_url_position(target_url, search_urls)
                        is_exposed = rank is not None
                        exposure_status = "O" if is_exposed else "X"

                    # 결과 데이터 구성
                    batch_updates.append({
                        'row': row,
                        'url': target_url,
                        'exposure_status': exposure_status,
                        'deletion_status': deletion_status,
                        'cross_keywords': cross_keywords,
                        'rank': rank,
                        'popular_status': popular_status,
                    })
                except Exception as e:
                    logging.error(f"행 {row} 처리 중 오류 발생, 건너뜀: {e}")
                    continue

        # 4. DB 일괄 업데이트
        if batch_updates:
            self.db_client.batch_update_monitoring_results(batch_updates)

        # 5. Google Sheets 동기화 (키워드순찰 시트 전체 갱신)
        if self.sheets_client:
            logging.info("Google Sheets 동기화 시작 (키워드순찰 시트)...")
            headers, rows = self.db_client.get_all_patrol_logs()
            if rows:
                self.sheets_client.sync_patrol_logs(headers, rows)
                logging.info("Google Sheets 동기화 완료")
            else:
                logging.warning("Google Sheets 동기화 대상 데이터 없음")

        # 작업 완료 후 드라이버 종료 (다음 실행 시 깨끗하게 시작)
        self.scraper.close_driver()

        return batch_updates

    def monitor_single_keyword(self, keyword: str, target_url: str) -> Dict:
        """
        단일 키워드 모니터링 (테스트/디버깅용)
        """
        soup = self.scraper.get_search_results(keyword, page=1)
        if not soup:
            return {'error': '검색 실패'}

        search_urls = self.scraper.extract_main_urls(soup)
        is_exposed = self.check_url_in_results(target_url, search_urls)
        position = self.find_url_position(target_url, search_urls) if is_exposed else None
        exposure_status = "O" if is_exposed else "X"

        return {
            'keyword': keyword,
            'target_url': target_url,
            'is_exposed': is_exposed,
            'exposure_status': exposure_status,
            'rank': position,
            'search_urls_count': len(search_urls)
        }

    def check_deleted_posts(self):
        """
        DB의 모든 게시글 삭제 여부 확인
        삭제된 글은 DB의 is_deleted=1로 업데이트
        """
        keywords = self.db_client.get_keywords_for_monitoring()

        if not keywords:
            logging.info("확인할 게시글이 없습니다.")
            return []

        # URL이 있고 아직 삭제되지 않은 항목만 필터링
        urls_to_check = [
            (item['target_url'], item['row'])
            for item in keywords
            if item.get('target_url') and item.get('is_deleted') != 'O'
        ]

        if not urls_to_check:
            logging.info("확인할 URL이 없습니다.")
            return []

        logging.info(f"\n총 {len(urls_to_check)}개의 게시글 삭제 여부를 확인합니다...")

        # 일괄 삭제 확인
        results = self.scraper.batch_check_posts_deleted(urls_to_check)

        # 삭제된 글의 DB id 수집
        deleted_ids = []
        deleted_count = 0

        for result in tqdm(results, desc="삭제 여부 확인 결과 처리"):
            if result['is_deleted']:
                deleted_count += 1
                deleted_ids.append(result['row'])
                logging.info(f"삭제된 글 발견 (id {result['row']}): {result['url']}")

        # DB 업데이트
        if deleted_ids:
            logging.info(f"\n{len(deleted_ids)}개의 삭제된 글을 DB에 업데이트 중...")
            self.db_client.mark_rows_deleted(deleted_ids)
            logging.info("업데이트 완료!")

        logging.info(f"\n삭제 확인 결과: 전체 {len(results)}개 중 {deleted_count}개 삭제됨")

        return results
