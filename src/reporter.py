import json
import os
import csv
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
        """
        키워드 노출 요약 생성
        - 노출되지 않은 키워드에 대해 가장 최근의 노출 일시(latest_exposed_at)와 해당 URL을 계산하여 추가
        """
        results = self.load_results()
        now = datetime.now()
        
        summary = {
            "timestamp": results["timestamp"],
            "category": self.category,
            "exposed": [],
            "not_exposed": [],
            "partially_exposed": [], # 일부 노출 키워드를 명확히 분리
            "skipped_keywords": []   # URL이 없어 건너뛴 키워드 (발행하지 않은 키워드)
        }
        
        for keyword_result in results["results"]:
            keyword = keyword_result["keyword"]
            urls = keyword_result["urls"]
            
            if not urls:
                # URL이 없는 키워드는 '발행하지 않은 키워드'로 분류
                summary["skipped_keywords"].append({
                    "keyword": keyword,
                    "status": "URL 없음"
                })
                continue
            
            # 노출 상태 확인 및 개수 계산
            exposed_count = sum(1 for url in urls if url.get("is_exposed"))
            total_count = len(urls)
            is_fully_exposed = (exposed_count == total_count)
            is_any_exposed = (exposed_count > 0)

            
            if is_fully_exposed:
                summary["exposed"].append({
                    "keyword": keyword,
                    "status": f"모든 URL 노출 ({exposed_count}/{total_count})"
                })
            elif is_any_exposed:
                # 일부 노출된 키워드
                summary["partially_exposed"].append({
                    "keyword": keyword,
                    "status": f"일부 URL 노출 ({exposed_count}/{total_count})"
                })
            else: # 모든 URL이 미노출된 경우 (🚨 노출 이탈 키워드)
                
                # 1. 모든 last_exposed_at 값과 URL 쌍 수집
                latest_exposed_data = [] # (datetime, url_raw)
                
                for url_entry in urls:
                    raw_date = url_entry.get('last_exposed_at')
                    if raw_date:
                        try:
                            dt = datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                            latest_exposed_data.append((dt, url_entry.get('url', '')))
                        except ValueError:
                            pass

                # 2. 가장 최근의 노출 일시 (Max) 찾기 및 해당 URL 추출
                latest_exposed_at = None
                latest_exposed_url = None
                
                if latest_exposed_data:
                    # 가장 최근 날짜를 기준으로 정렬 (내림차순)
                    latest_exposed_data.sort(key=lambda x: x[0], reverse=True)
                    latest_exposed_at = latest_exposed_data[0][0]
                    latest_exposed_url = latest_exposed_data[0][1]
                
                # 3. 출력 정보 생성
                days_since_exposure = None
                last_exposed_info_str = "기록 없음"
                
                if latest_exposed_at:
                    # 현재 시간과의 차이 계산
                    days_since_exposure = (now - latest_exposed_at).days
                    
                    last_exposed_info_str = f"{latest_exposed_at.strftime('%Y-%m-%d %H:%M:%S')} (D+{days_since_exposure})"
                
                
                summary["not_exposed"].append({
                    "keyword": keyword,
                    "status": f"노출 없음 (0/{total_count})",
                    "latest_exposed_at": latest_exposed_at,      # 정렬 및 추가 처리용 datetime 객체
                    "latest_exposed_str": last_exposed_info_str, # HTML 출력용 문자열
                    "latest_exposed_url": latest_exposed_url     # CSV용 대표 URL
                })
                
        return results, summary # 원본 결과와 요약 모두 반환
        
    def export_csv_for_unexposed(self, all_results, summary):
        """
        노출되지 않은 키워드에 대한 상세 정보를 CSV 파일로 저장합니다.
        키워드당 가장 최근 노출 기록을 가진 URL 하나만 표시합니다.
        """
        # 출력 경로 설정
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        csv_filename = f'unexposed_keywords_summary_{self.category}.csv'
        csv_path = os.path.join(OUTPUT_DIR, csv_filename)
        
        # '노출 이탈 키워드' 리스트에서 필요한 정보만 추출
        header = ["카테고리", "키워드", "대표 URL", "마지막 노출일시"]
        data_rows = []
        
        # summary["not_exposed"]에 이미 키워드별 대표 정보가 모두 계산되어 있습니다.
        for item in summary["not_exposed"]:
            
            # last_exposed_at을 문자열 형식으로 가져오되, 기록이 없으면 "기록 없음"으로 표시
            last_exposed_str = item["latest_exposed_at"].strftime("%Y-%m-%d %H:%M:%S") if item["latest_exposed_at"] else "기록 없음"
            
            row = [
                self.category,
                item["keyword"],
                item["latest_exposed_url"] if item["latest_exposed_url"] else "N/A", # 대표 URL
                last_exposed_str
            ]
            
            data_rows.append(row)

        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data_rows)
            
        print(f"노출 이탈 키워드 요약 CSV가 {csv_path}에 저장되었습니다.")
        return csv_path, csv_filename

    def print_report(self):
        """콘솔에 보고서 출력"""
        _, summary = self.generate_summary() # summary만 사용
        
        print("\n" + "=" * 50)
        print(f" 네이버 검색 노출 모니터링 보고서 - {self.category.upper()}")
        print("=" * 50)
        print(f"생성 시간: {summary['timestamp']}")
        
        # 1. 노출된 키워드 (전체 + 일부)
        all_exposed = summary["exposed"] + summary["partially_exposed"]
        print("\n[✅ 노출된 키워드 (전체 및 일부)]")
        if all_exposed:
            exposed_data = [(item["keyword"], item["status"]) for item in all_exposed]
            print(tabulate(exposed_data, headers=["키워드", "상태"], tablefmt="grid"))
        else:
            print("노출된 키워드가 없습니다.")

        # 2. 노출 이탈 키워드 (조치 필요)
        print("\n[🚨 노출 이탈 키워드 (조치 필요)]")
        if summary["not_exposed"]:
            # HTML용 문자열 필드 사용
            not_exposed_data = [
                (item["keyword"], item["status"], item["latest_exposed_str"]) 
                for item in summary["not_exposed"]
            ]
            print(tabulate(not_exposed_data, headers=["키워드", "상태", "마지막 노출일시"], tablefmt="grid"))
        else:
            print("노출 이탈 키워드가 없습니다.")
            
        # 3. 발행하지 않은 키워드 (URL 없음)
        print("\n[📝 발행하지 않은 키워드 (URL 설정 없음)]")
        if summary["skipped_keywords"]:
            skipped_data = [(item["keyword"], item["status"]) for item in summary["skipped_keywords"]]
            print(tabulate(skipped_data, headers=["키워드", "상태"], tablefmt="grid"))
        else:
            print("발행하지 않은 키워드가 없습니다.")
            
    def export_json(self):
        """JSON 형식으로 처리된 결과 내보내기 - 정확한 형식 유지"""
        results, _ = self.generate_summary() # 원본 결과만 사용
        
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