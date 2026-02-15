"""
보고서 생성 모듈 - Google Sheets 기반
"""

import os
import csv
from datetime import datetime
from tabulate import tabulate
from typing import List, Dict
from src.config import OUTPUT_DIR
import logging

class Reporter:
    """Google Sheets 기반 보고서 생성 클래스"""

    def __init__(self, sheets_client):
        """
        초기화

        Args:
            sheets_client: GoogleSheetsClient 인스턴스
        """
        self.sheets_client = sheets_client

    def generate_summary(self) -> Dict:
        """
        Google Sheets에서 키워드 노출 요약 생성

        Returns:
            {
                'timestamp': '2026-01-29 10:00:00',
                'total': 100,
                'exposed': [...],
                'not_exposed': [...],
                'no_url': [...]
            }
        """
        keywords_data = self.sheets_client.get_keywords_data()
        now = datetime.now()

        summary = {
            'timestamp': now.strftime("%Y-%m-%d %H:%M:%S"),
            'total': len(keywords_data),
            'exposed': [],      # 노출된 키워드
            'not_exposed': [],  # 미노출 키워드
            'no_url': []        # URL 없는 키워드
        }

        for data in keywords_data:
            keyword = data.get('keyword', '')
            post_url = data.get('post_url', '')
            exposure_status = data.get('exposure_status', '')
            update_date = data.get('update_date', '')
            top_author = data.get('top_author', '')
            top_cafe_url = data.get('top_cafe_url', '')
            publish_time = data.get('publish_time', '')

            # URL이 없는 키워드
            if not post_url:
                summary['no_url'].append({
                    'keyword': keyword,
                    'status': 'URL 없음',
                    'publish_time': publish_time
                })
                continue

            # 노출 상태 확인 (O: 노출, X: 미노출)
            if exposure_status == 'O':
                summary['exposed'].append({
                    'keyword': keyword,
                    'status': 'O',
                    'patrol_time': data.get('patrol_time', ''),
                    'publish_time': publish_time
                })
            else:
                summary['not_exposed'].append({
                    'keyword': keyword,
                    'status': 'X',
                    'post_url': post_url,
                    'patrol_time': data.get('patrol_time', ''),
                    'publish_time': publish_time
                })

        return summary

    def print_report(self):
        """콘솔에 보고서 출력"""
        summary = self.generate_summary()

        logging.info("\n" + "=" * 60)
        logging.info(" 네이버 검색 노출 모니터링 보고서 (Google Sheets)")
        logging.info("=" * 60)
        logging.info(f"생성 시간: {summary['timestamp']}")
        logging.info(f"총 키워드 수: {summary['total']}")

        # 1. 노출된 키워드 (O)
        logging.info(f"\n[✅ 노출 (O)] ({len(summary['exposed'])}개)")
        if summary['exposed']:
            exposed_data = [
                (item['keyword'], item['status'], item.get('patrol_time', ''))
                for item in summary['exposed']
            ]
            logging.info(tabulate(exposed_data,
                           headers=["키워드", "노출", "순찰시간"],
                           tablefmt="grid"))
        else:
            logging.info("노출된 키워드가 없습니다.")

        # 2. 미노출 키워드 (X)
        logging.info(f"\n[❌ 미노출 (X)] ({len(summary['not_exposed'])}개)")
        if summary['not_exposed']:
            not_exposed_data = [
                (item['keyword'], item['status'], item.get('patrol_time', ''))
                for item in summary['not_exposed']
            ]
            logging.info(tabulate(not_exposed_data,
                           headers=["키워드", "노출", "순찰시간"],
                           tablefmt="grid"))
        else:
            logging.info("미노출 키워드가 없습니다.")

        # 3. URL 없는 키워드
        logging.info(f"\n[📝 URL 미설정 키워드] ({len(summary['no_url'])}개)")
        if summary['no_url']:
            no_url_data = [(item['keyword'], item['status']) for item in summary['no_url']]
            logging.info(tabulate(no_url_data,
                           headers=["키워드", "상태"],
                           tablefmt="grid"))
        else:
            logging.info("URL 미설정 키워드가 없습니다.")

        # 요약 통계
        logging.info("\n" + "-" * 60)
        logging.info(f"✅ 노출: {len(summary['exposed'])}개")
        logging.info(f"🚨 미노출: {len(summary['not_exposed'])}개")
        logging.info(f"📝 URL 미설정: {len(summary['no_url'])}개")
        logging.info("-" * 60)

    def export_csv_for_unexposed(self) -> str:
        """
        미노출 키워드를 CSV 파일로 내보내기

        Returns:
            저장된 CSV 파일 경로
        """
        summary = self.generate_summary()

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        csv_filename = 'unexposed_keywords.csv'
        csv_path = os.path.join(OUTPUT_DIR, csv_filename)

        header = ["키워드", "상태", "작성글 URL", "마지막 업데이트"]
        data_rows = []

        for item in summary['not_exposed']:
            row = [
                item['keyword'],
                item['status'],
                item.get('post_url', ''),
                item.get('update_date', '')
            ]
            data_rows.append(row)

        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data_rows)

        logging.info(f"미노출 키워드 CSV가 {csv_path}에 저장되었습니다.")
        return csv_path

    def get_statistics(self) -> Dict:
        """
        통계 정보 반환

        Returns:
            {
                'total': 100,
                'exposed_count': 80,
                'not_exposed_count': 15,
                'no_url_count': 5,
                'exposure_rate': 84.2
            }
        """
        summary = self.generate_summary()

        total_with_url = len(summary['exposed']) + len(summary['not_exposed'])
        exposure_rate = (len(summary['exposed']) / total_with_url * 100) if total_with_url > 0 else 0

        return {
            'total': summary['total'],
            'exposed_count': len(summary['exposed']),
            'not_exposed_count': len(summary['not_exposed']),
            'no_url_count': len(summary['no_url']),
            'exposure_rate': round(exposure_rate, 1)
        }

    def print_statistics(self):
        """통계 정보 출력"""
        stats = self.get_statistics()

        logging.info("\n" + "=" * 40)
        logging.info(" 키워드 노출 통계")
        logging.info("=" * 40)
        logging.info(f"총 키워드: {stats['total']}개")
        logging.info(f"노출: {stats['exposed_count']}개")
        logging.info(f"미노출: {stats['not_exposed_count']}개")
        logging.info(f"URL 미설정: {stats['no_url_count']}개")
        logging.info(f"노출률: {stats['exposure_rate']}%")
        logging.info("=" * 40)
