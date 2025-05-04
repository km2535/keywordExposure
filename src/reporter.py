import json
import os
import pandas as pd
from datetime import datetime
from tabulate import tabulate

class Reporter:
    def __init__(self, results_path):
        self.results_path = results_path
        
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
        print(" 네이버 검색 노출 모니터링 보고서")
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
            
    def export_csv(self):
        """CSV 형식으로 보고서 내보내기 (keyword-exposure/public/data 경로에 저장)"""
        results = self.load_results()
        
        # 고정 출력 경로 설정
        output_dir = '/var/www/keywordE/build/data'
        os.makedirs(output_dir, exist_ok=True)
        
        # CSV 파일명
        csv_filename = 'latest_results.csv'
        output_path = os.path.join(output_dir, csv_filename)
        
        # JSON 파일명 (가능하면 JSON도 최신 상태로 유지)
        json_filename = 'latest_results.json'
        json_path = os.path.join(output_dir, json_filename)
        
        # 데이터 프레임 변환을 위한 리스트 생성
        data = []
        
        for keyword_result in results["results"]:
            keyword = keyword_result["keyword"]
            
            if not keyword_result["urls"]:  # URL이 없는 경우
                data.append({
                    "키워드": keyword,
                    "URL": "",
                    "상태": "URL 없음",
                    "확인 시간": results["timestamp"]
                })
            else:
                for url_result in keyword_result["urls"]:
                    url = url_result["url"]
                    status = "노출" if url_result["is_exposed"] else "미노출"
                    
                    data.append({
                        "키워드": keyword,
                        "URL": url,
                        "상태": status,
                        "확인 시간": results["timestamp"]
                    })
                
        # 데이터프레임 생성 및 저장 (덮어쓰기)
        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"CSV 보고서가 {output_path}에 저장되었습니다.")
        
        # JSON 결과도 같은 위치에 복사 (덮어쓰기)
        import shutil
        shutil.copy2(self.results_path, json_path)
        print(f"JSON 결과가 {json_path}에 복사되었습니다.")
        
        return output_path
    
    def export_json(self):
        """JSON 형식으로 처리된 결과 내보내기 (키워드별 노출 상태 분석 포함)"""
        summary = self.generate_summary()
        results = self.load_results()
        
        # 고정 출력 경로 설정
        output_dir = '/var/www/keywordE/build/data'
        os.makedirs(output_dir, exist_ok=True)
        json_path = os.path.join(output_dir, 'latest_results.json')
        
        # 노출 상태 정보 추가
        for keyword_result in results["results"]:
            keyword = keyword_result["keyword"]
            urls = keyword_result["urls"]
            
            # 노출된 URL 개수 확인
            exposed_count = sum(1 for url in urls if url["is_exposed"]) if urls else 0
            total_count = len(urls) if urls else 0
            
            # 노출 상태 추가
            if total_count == 0:
                exposure_status = "URL 없음"
            elif exposed_count == 0:
                exposure_status = "노출 안됨"
            elif exposed_count == total_count:
                exposure_status = "모두 노출됨"
            else:
                exposure_status = "일부 노출됨"
                
            keyword_result["exposure_status"] = exposure_status
            keyword_result["exposed_count"] = exposed_count
            keyword_result["total_urls"] = total_count
        
        # JSON 파일로 저장 (덮어쓰기)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        print(f"분석된 JSON 결과가 {json_path}에 저장되었습니다.")
        return json_path
