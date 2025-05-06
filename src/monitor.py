import json
import os
from datetime import datetime
from tqdm import tqdm
from src.config import DATA_DIR

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
        
    def save_results(self, results):
        """결과 저장"""
        # 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(self.results_path), exist_ok=True)
        
        with open(self.results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
    def check_url_in_results(self, url, search_urls):
        """URL이 검색 결과에 있는지 확인"""
        # URL 정규화 및 비교 로직을 향상시킬 수 있음
        for search_url in search_urls:
            if url in search_url or search_url in url:
                return True
        return False
        
    def monitor_keywords(self, pages_to_check=1):
        """모든 키워드 모니터링 - 1페이지만 검색"""
        config = self.load_keywords()
        results = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "results": []
        }
        
        # URL이 있는 키워드만 필터링
        valid_keywords = [item for item in config['keywords'] if item["urls"]]
        skipped_keywords = [item for item in config['keywords'] if not item["urls"]]
        
        print(f"총 {len(valid_keywords)} 개의 키워드를 모니터링합니다...")
        if skipped_keywords:
            print(f"{len(skipped_keywords)} 개의 키워드는 URL이 없어 건너뜁니다.")
        
        for item in tqdm(valid_keywords, desc="키워드 검색 중"):
            keyword = item["keyword"]
            target_urls = item["urls"]
            
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
            for url in target_urls:
                is_exposed = self.check_url_in_results(url, all_search_urls)
                status = "노출" if is_exposed else "미노출"
                print(f"  URL '{url}' - {status}")
                
                url_results.append({
                    "url": url,
                    "is_exposed": is_exposed
                })
                
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