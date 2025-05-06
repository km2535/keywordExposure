import os
import argparse
import time
from src.scraper import NaverScraper
from src.monitor import KeywordMonitor
from src.reporter import Reporter
from src.config import CONFIG_DIR, DATA_DIR, CATEGORIES, DEFAULT_PAGES, OUTPUT_DIR

def main():
    print("실행")
    parser = argparse.ArgumentParser(description='네이버 검색 노출 모니터링 도구')
    parser.add_argument('--pages', type=int, default=DEFAULT_PAGES, help='검색할 페이지 수')
    parser.add_argument('--report', action='store_true', help='최신 결과 보고서 생성')
    parser.add_argument('--category', type=str, default='cancer', 
                      help=f'키워드 카테고리 ({", ".join(CATEGORIES)})')
    parser.add_argument('--all-categories', action='store_true',
                      help='모든 카테고리 실행')
    
    args = parser.parse_args()
    
    # 필요한 디렉토리 생성
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 실행할 카테고리 목록
    categories_to_run = CATEGORIES if args.all_categories else [args.category]
    for category in categories_to_run:
        print(f"\n===== 카테고리: {category} =====")
        
        # 경로 설정
        config_path = os.path.join(CONFIG_DIR, f'keywords_{category}.json')
        results_path = os.path.join(DATA_DIR, f'latest_results_{category}.json')
        
        # 설정 파일이 없는 경우 건너뛰기
        if not os.path.exists(config_path):
            print(f"경고: 설정 파일이 없습니다: {config_path}")
            print(f"{category} 카테고리를 건너뜁니다.")
            continue
        
        # 객체 초기화
        scraper = NaverScraper()
        monitor = KeywordMonitor(scraper, config_path, results_path)
        reporter = Reporter(results_path, category)
        
        # 보고서 생성 모드
        if args.report:
            try:
                reporter.print_report()
                # JSON 내보내기
                reporter.export_json()
            except FileNotFoundError as e:
                print(f"오류: {e}")
                print("먼저 모니터링을 실행해주세요.")
            continue
        
        # 모니터링 실행
        print(f"{category} 카테고리에 대한 네이버 검색 노출 모니터링을 시작합니다...")
        results = monitor.monitor_keywords(pages_to_check=args.pages)
        
        # 결과 보고서 출력
        reporter.print_report()
        
        # JSON 내보내기
        reporter.export_json()

if __name__ == "__main__":
    main()