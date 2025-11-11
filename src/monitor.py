import json
import os
from datetime import datetime
from tqdm import tqdm
from src.config import DATA_DIR
from urllib.parse import urlparse

class KeywordMonitor:
    def __init__(self, scraper, config_path, results_path):
        self.scraper = scraper
        self.config_path = config_path
        self.results_path = results_path
        
    def load_keywords(self):
        """키워드 및 URL 설정 로드"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"경고: 설정 파일을 찾을 수 없습니다: {self.config_path}")
            # 빈 키워드 목록 반환
            return {"keywords": []}
            
    def load_previous_results_map(self):
        previous_map = {}
        if os.path.exists(self.results_path):
            try:
                with open(self.results_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    for keyword_result in data.get("results", []):
                        keyword = keyword_result["keyword"]
                        
                        url_map = {}
                        for url_entry in keyword_result["urls"]:
                            # 1. URL 정규화 적용 (이전 데이터 로드 시점)
                            url = self.normalize_url(url_entry["url"])
                            
                            url_map[url] = {
                                'is_exposed': url_entry.get('is_exposed', False),
                                'last_exposed_at': url_entry.get('last_exposed_at')
                            }
                        
                        previous_map[keyword] = url_map
                    return previous_map
            except Exception as e:
                print(f"경고: 이전 결과 로드 중 오류 발생 - {e}. 새 파일로 시작합니다.")
                return {}
        return {} 
        
    def save_results(self, results):
        """결과 저장"""
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(self.results_path), exist_ok=True)
        
        with open(self.results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
    
    def normalize_url(self, url):
        """
        URL 정규화: 네이버 URL의 모바일 'm.'을 제거하고 쿼리 파라미터를 제외합니다.
        """
        parsed = urlparse(url)
        # 네이버 모바일 카페/블로그 URL은 netloc에서 'm.'을 제거하여 정규화
        normalized_netloc = parsed.netloc.replace('m.', '')
        
        # 쿼리 파라미터는 비교에서 제외
        return normalized_netloc + parsed.path

    def check_url_in_results(self, url, search_urls):
        """
        타겟 URL이 검색 결과에 포함되어 있는지 확인합니다.
        (정규화된 URL 기준으로 비교)
        """
        target = self.normalize_url(url)
        for search_url in search_urls:
            # 검색 결과의 URL도 정규화하여 비교
            if self.normalize_url(search_url) == target:
                return True
        return False
        
    def monitor_keywords(self, pages_to_check=1):
        """모든 키워드 모니터링 - 1페이지만 검색"""
        config = self.load_keywords()
        
        # 1. 이전 결과 로드
        previous_results_map = self.load_previous_results_map()

        results = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "results": []
        }
        
        # 현재 시간 문자열 (is_exposed=True일 때 기록할 시간)
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # URL이 있는 키워드만 필터링
        valid_keywords = [item for item in config['keywords'] if item["urls"]]
        skipped_keywords = [item for item in config['keywords'] if not item["urls"]]
        
        print(f"총 {len(valid_keywords)} 개의 키워드를 모니터링합니다...")
        if skipped_keywords:
            print(f"{len(skipped_keywords)} 개의 키워드는 URL이 없어 건너뜁니다.")
        
        for item in tqdm(valid_keywords, desc="키워드 검색 중"):
            keyword = item["keyword"]
            target_urls_raw = item["urls"]
            
            print(f"\n키워드 '{keyword}' 검색 중...")
            all_search_urls = []
            
            # 1페이지만 검색
            page = 1
            print(f"  페이지 {page} 검색 중...")
            soup = self.scraper.get_search_results(keyword, page=page)
            if soup:
                page_urls = self.scraper.extract_urls(soup)
                all_search_urls.extend(page_urls)
                print(f"  페이지 {page}에서 {len(page_urls)}개의 URL을 찾았습니다.")
            
            # 각 URL 노출 여부 확인
            url_results = []
            for url_raw in target_urls_raw:
                is_exposed = self.check_url_in_results(url_raw, all_search_urls)
                status = "노출" if is_exposed else "미노출"
                
                # 타겟 URL을 정규화된 키로 사용
                url_normalized = self.normalize_url(url_raw)

                # 이전 데이터 가져오기 (정규화된 URL 키 사용)
                previous_data = previous_results_map.get(keyword, {}).get(url_normalized, {})
                old_last_exposed_at = previous_data.get('last_exposed_at')
                
                # 마지막 노출 시간 업데이트 로직
                # 1. 이번에 노출된 경우: 현재 시간으로 갱신
                if is_exposed:
                    last_exposed_at_to_save = current_time_str
                # 2. 이번에 미노출된 경우: 이전의 마지막 노출 시간 유지 (상실 시점 추적)
                else:
                    last_exposed_at_to_save = old_last_exposed_at
                
                print(f"  URL '{url_raw}' - {status}")
                
                url_entry = {
                    # 결과 파일에는 원본 URL을 저장
                    "url": url_raw,
                    "is_exposed": is_exposed
                }
                
                # last_exposed_at 값이 있으면 추가
                if last_exposed_at_to_save:
                    url_entry["last_exposed_at"] = last_exposed_at_to_save
                
                url_results.append(url_entry)
                
            keyword_result = {
                "keyword": keyword,
                "urls": url_results
            }
            
            results["results"].append(keyword_result)
        
        # URL이 없는 키워드도 결과에 포함 (하지만 검색은 하지 않음)
        for item in skipped_keywords:
            keyword_result = {
                "keyword": item["keyword"],
                "urls": []
            }
            results["results"].append(keyword_result)
            
        self.save_results(results)
        print(f"\n모니터링 결과가 {self.results_path}에 저장되었습니다.")
        return results