import json
import os
from datetime import datetime
from tabulate import tabulate
from src.config import OUTPUT_DIR, DATA_DIR

class Reporter:
    def __init__(self, results_path, category='cancer'):
        self.results_path = results_path
        self.category = category
        
    def load_results(self):
        """결과 파일 로드"""
        if not os.path.exists(self.results_path):
            raise FileNotFoundError(f"결과 파일을 찾을 수 없습니다: {self.results_path}")
            
        with open(self.results_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    def generate_summary(self):
        """키워드 노출 요약 생성"""
        results = self.load_results()
        
        summary = {
            "timestamp": results["timestamp"],
            "category": self.category,
            "exposed": [],
            "not_exposed": []
        }
        
        for keyword_result in results["results"]:
            keyword = keyword_result["keyword"]
            urls = keyword_result["urls"]
            
            # 모든 URL이 노출되었는지 확인
            all_exposed = all(url["is_exposed"] for url in urls) if urls else False
            any_exposed = any(url["is_exposed"] for url in urls) if urls else False
            
            # 노출된 URL 개수 확인
            exposed_count = sum(1 for url in urls if url["is_exposed"])
            total_count = len(urls)
            
            if all_exposed and total_count > 0:
                summary["exposed"].append({
                    "keyword": keyword,
                    "status": f"모든 URL 노출 ({exposed_count}/{total_count})"
                })
            elif any_exposed:
                summary["exposed"].append({
                    "keyword": keyword,
                    "status": f"일부 URL 노출 ({exposed_count}/{total_count})"
                })
            else:
                summary["not_exposed"].append({
                    "keyword": keyword,
                    "status": f"노출 없음 (0/{total_count})"
                })
                
        return summary
        
    def print_report(self):
        """콘솔에 보고서 출력"""
        summary = self.generate_summary()
        
        print("\n" + "=" * 50)
        print(f" 네이버 검색 노출 모니터링 보고서 - {self.category.upper()}")
        print("=" * 50)
        print(f"생성 시간: {summary['timestamp']}")
        
        print("\n[노출된 키워드]")
        if summary["exposed"]:
            exposed_data = [(item["keyword"], item["status"]) for item in summary["exposed"]]
            print(tabulate(exposed_data, headers=["키워드", "상태"], tablefmt="grid"))
        else:
            print("노출된 키워드가 없습니다.")
            
        print("\n[노출되지 않은 키워드]")
        if summary["not_exposed"]:
            not_exposed_data = [(item["keyword"], item["status"]) for item in summary["not_exposed"]]
            print(tabulate(not_exposed_data, headers=["키워드", "상태"], tablefmt="grid"))
        else:
            print("모든 키워드가 노출되었습니다.")
    
    def export_json(self):
        """JSON 형식으로 처리된 결과 내보내기 - 정확한 형식 유지"""
        results = self.load_results()
        
        # 출력 경로 설정
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        json_path = os.path.join(OUTPUT_DIR, f'latest_results_{self.category}.json')
        
        # 원본 JSON 구조 유지
        export_data = {
            "timestamp": results["timestamp"],
            "results": results["results"]
        }
        
        # JSON 파일로 저장 (덮어쓰기)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=4)
            
        print(f"JSON 결과가 {json_path}에 저장되었습니다.")
        return json_path