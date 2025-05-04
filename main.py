import os
import argparse
import time
from src.scraper import NaverScraper
from src.monitor import KeywordMonitor
from src.reporter import Reporter

def main():
    print("실행")
    parser = argparse.ArgumentParser(description='네이버 검색 노출 모니터링 도구')
    parser.add_argument('--pages', type=int, default=3, help='검색할 페이지 수')
    parser.add_argument('--report', action='store_true', help='최신 결과 보고서 생성')
    parser.add_argument('--export', action='store_true', help='CSV로 결과 내보내기')
    parser.add_argument('--config', type=str, default='config/keywords.json', help='키워드 설정 파일 경로')
    
    args = parser.parse_args()
    
    # 경로 설정
    config_path = args.config
    results_path = os.path.join('data', 'latest_results.json')
    
    # 객체 초기화
    scraper = NaverScraper()
    monitor = KeywordMonitor(scraper, config_path, results_path)
    reporter = Reporter(results_path)
    
    # 보고서 생성 모드
    if args.report:
        try:
            reporter.print_report()
            if args.export:
                reporter.export_csv()
        except FileNotFoundError as e:
            print(f"오류: {e}")
            print("먼저 모니터링을 실행해주세요.")
        return
    
    # 모니터링 실행
    print("네이버 검색 노출 모니터링을 시작합니다...")
    results = monitor.monitor_keywords(pages_to_check=args.pages)
    
    # 결과 보고서 출력
    reporter.print_report()
    
    # CSV 내보내기 (요청 시)
    if args.export:
        reporter.export_csv()

if __name__ == "__main__":
    main()
