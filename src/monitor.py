"""
키워드 모니터링 모듈 - Google Sheets 기반
"""

from datetime import datetime
from tqdm import tqdm
from urllib.parse import urlparse
from typing import List, Dict, Optional
import logging

class KeywordMonitor:
    """Google Sheets 기반 키워드 모니터링 클래스"""

    def __init__(self, scraper, sheets_client):
        """
        초기화

        Args:
            scraper: NaverScraper 인스턴스
            sheets_client: GoogleSheetsClient 인스턴스
        """
        self.scraper = scraper
        self.sheets_client = sheets_client

    def normalize_url(self, url: str) -> str:
        """
        URL 정규화: 네이버 URL의 모바일 'm.'을 제거하고 쿼리 파라미터를 제외
        """
        if not url:
            return ''
        parsed = urlparse(url)
        # 네이버 모바일 카페/블로그 URL은 netloc에서 'm.'을 제거하여 정규화
        normalized_netloc = parsed.netloc.replace('m.', '')

        # 쿼리 파라미터는 비교에서 제외
        return normalized_netloc + parsed.path

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

    def find_top_cafe_info(self, search_urls: List[str], cafe_list: List[Dict]) -> Dict:
        """
        검색 결과에서 우리 카페 중 최상단 정보 찾기

        Args:
            search_urls: 검색 결과 URL 목록
            cafe_list: 카페 목록 [{'cafe_name': '...', 'cafe_id': '...'}, ...]

        Returns:
            {
                'position': 3,  # 순위 (1-based)
                'url': 'https://...',
                'cafe_name': '천아베베',
                'cafe_id': 'camsbaby'
            }
            또는 찾지 못하면 None
        """
        # 카페 ID 집합 생성
        our_cafe_ids = {cafe['cafe_id'].lower() for cafe in cafe_list}
        cafe_id_to_name = {cafe['cafe_id'].lower(): cafe['cafe_name'] for cafe in cafe_list}

        for idx, search_url in enumerate(search_urls, start=1):
            cafe_id = self.get_cafe_id_from_url(search_url)
            if cafe_id and cafe_id.lower() in our_cafe_ids:
                return {
                    'position': idx,
                    'url': search_url,
                    'cafe_name': cafe_id_to_name.get(cafe_id.lower(), ''),
                    'cafe_id': cafe_id
                }
        return None

    def monitor_keywords(self):
        """
        Google Sheets 기반 키워드 모니터링
        같은 키워드는 한 번만 검색하되, 각 URL의 삭제 여부는 개별적으로 확인합니다.
        매 실행 시 캐시와 쿠키를 초기화하여 깨끗한 상태에서 시작합니다.
        """
        # 캐시/쿠키 초기화: 이전 드라이버가 남아있으면 완전히 리셋
        self.scraper.reset_driver()
        print("캐시/쿠키 초기화 완료 - 깨끗한 상태에서 모니터링을 시작합니다.")

        keywords_data = self.sheets_client.get_keywords_for_monitoring()
        if not keywords_data:
            return []

        # 1. 키워드별로 데이터 그룹화 (검색 횟수 최소화 목적)
        keyword_groups = {}
        for item in keywords_data:
            if item.get('is_deleted') == 'O': # 이미 삭제된 행은 제외
                continue
            
            kw = item['keyword']
            if kw not in keyword_groups:
                keyword_groups[kw] = []
            keyword_groups[kw].append(item)

        batch_updates = []

        # 2. 키워드별 루프
        for keyword, items in tqdm(keyword_groups.items(), desc="키워드별 모니터링 진행 중"):
            
            # 해당 키워드의 네이버 검색 결과는 한 번만 가져옴
            # data-heatmap-target=".link" 인 메인 노출 URL만 사용
            soup = self.scraper.get_search_results(keyword, page=1)
            search_urls = self.scraper.extract_main_urls(soup) if soup else []

            # 3. 같은 키워드 내의 각 URL(행)들을 개별 검사
            for item in items:
                target_url = item['target_url']
                row = item['row']

                # [개별 확인] 게시글 삭제 여부를 URL마다 각각 확인
                is_deleted, _ = self.scraper.check_post_deleted(target_url)

                if is_deleted:
                    # 삭제된 경우: 노출 X, 삭제 O
                    exposure_status = "X"
                    deletion_status = "O"
                else:
                    # 살아있는 경우: 검색 결과(search_urls)에 포함되었는지 확인
                    deletion_status = "X"
                    is_exposed = self.check_url_in_results(target_url, search_urls)
                    exposure_status = "O" if is_exposed else "X"

                # 결과 데이터 구성
                batch_updates.append({
                    'row': row,
                    'exposure_status': exposure_status,
                    'deletion_status': deletion_status 
                })

        # 4. Google Sheets 일괄 업데이트
        if batch_updates:
            self.sheets_client.batch_update_monitoring_results(batch_updates)

        # 작업 완료 후 드라이버 종료 (다음 실행 시 깨끗하게 시작)
        self.scraper.close_driver()

        return batch_updates

    def monitor_single_keyword(self, keyword: str, target_url: str, row: int) -> Dict:
        """
        단일 키워드 모니터링 (테스트/디버깅용)
        """
        cafe_list = self.sheets_client.get_cafe_list()

        soup = self.scraper.get_search_results(keyword, page=1)
        if not soup:
            return {'error': '검색 실패'}

        # data-heatmap-target=".link" 인 메인 노출 URL만 사용
        search_urls = self.scraper.extract_main_urls(soup)
        is_exposed = self.check_url_in_results(target_url, search_urls)
        position = self.find_url_position(target_url, search_urls) if is_exposed else None
        top_cafe_info = self.find_top_cafe_info(search_urls, cafe_list) if cafe_list else None

        exposure_status = "O" if is_exposed else "X"

        return {
            'keyword': keyword,
            'target_url': target_url,
            'is_exposed': is_exposed,
            'exposure_status': exposure_status,
            'search_urls_count': len(search_urls)
        }

    def check_deleted_posts(self):
        """
        Google Sheets의 모든 게시글 삭제 여부 확인
        삭제된 글은 '삭제' 컬럼에 'O' 표시
        """
        # 모니터링할 키워드 목록 가져오기
        keywords = self.sheets_client.get_keywords_for_monitoring()

        if not keywords:
            logging.info("확인할 게시글이 없습니다.")
            return []

        # URL이 있는 항목만 필터링
        urls_to_check = [
            (item['target_url'], item['row'])
            for item in keywords
            if item.get('target_url')
        ]

        if not urls_to_check:
            logging.info("확인할 URL이 없습니다.")
            return []

        logging.info(f"\n총 {len(urls_to_check)}개의 게시글 삭제 여부를 확인합니다...")

        # 일괄 삭제 확인
        results = self.scraper.batch_check_posts_deleted(urls_to_check)

        # 삭제된 글 업데이트
        batch_updates = []
        deleted_count = 0

        for result in tqdm(results, desc="삭제 여부 확인 결과 처리"):
            if result['is_deleted']:
                deleted_count += 1
                batch_updates.append({
                    'row': result['row'],
                    'column': '삭제',
                    'value': 'O'
                })
                logging.info(f"  🗑️ 삭제된 글 발견 (행 {result['row']}): {result['url']}")

        # 결과를 Google Sheets에 업데이트
        if batch_updates:
            logging.info(f"\n{len(batch_updates)}개의 삭제된 글을 Google Sheets에 업데이트 중...")
            self.sheets_client.batch_update_cells(batch_updates)
            logging.info("업데이트 완료!")

        logging.info(f"\n삭제 확인 결과: 전체 {len(results)}개 중 {deleted_count}개 삭제됨")

        return results

    def monitor_and_check_deleted(self):
        """
        키워드 모니터링 + 삭제 확인을 함께 수행
        """
        logging.info("=" * 60)
        logging.info(" 1단계: 키워드 노출 모니터링")
        logging.info("=" * 60)
        monitoring_results = self.monitor_keywords()

        logging.info("\n")
        logging.info("=" * 60)
        logging.info(" 2단계: 게시글 삭제 여부 확인")
        logging.info("=" * 60)
        deletion_results = self.check_deleted_posts()

        return {
            'monitoring': monitoring_results,
            'deletion': deletion_results
        }
