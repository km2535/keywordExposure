"""
Google Sheets API 연동 모듈
- 키워드 데이터 읽기/쓰기
- 모니터링 결과 업데이트
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from typing import List, Dict, Optional
import time

# Google Sheets API 스코프
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]


class GoogleSheetsClient:
    """Google Sheets 클라이언트 클래스"""

    def __init__(self, credentials_path: str, spreadsheet_id: str, sheet_gid: int = 0):
        """
        초기화

        Args:
            credentials_path: 서비스 계정 JSON 키 파일 경로
            spreadsheet_id: Google Sheets 문서 ID
            sheet_gid: 시트 GID (기본값: 0)
        """
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        self.sheet_gid = sheet_gid
        self.client = None
        self.spreadsheet = None
        self.worksheet = None
        self._headers_cache = None

    def connect(self):
        """Google Sheets에 연결"""
        try:
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)

            # GID로 워크시트 찾기
            self.worksheet = self._get_worksheet_by_gid(self.sheet_gid)

            # 헤더 캐시
            self._headers_cache = None

            print(f"Google Sheets 연결 성공: {self.spreadsheet.title}")
            return True
        except Exception as e:
            print(f"Google Sheets 연결 실패: {e}")
            return False

    def _get_worksheet_by_gid(self, gid: int):
        """GID로 워크시트 찾기"""
        for ws in self.spreadsheet.worksheets():
            if ws.id == gid:
                return ws
        # GID를 찾지 못하면 첫 번째 시트 반환
        print(f"경고: GID {gid}를 찾을 수 없어 첫 번째 시트를 사용합니다.")
        return self.spreadsheet.sheet1

    def get_all_data(self) -> List[Dict]:
        """
        시트의 모든 데이터를 딕셔너리 리스트로 반환
        첫 번째 행을 헤더로 사용
        (중복 헤더 문제를 우회하기 위해 수동으로 처리)
        """
        if not self.worksheet:
            raise Exception("워크시트가 연결되지 않았습니다. connect()를 먼저 호출하세요.")

        # get_all_records()는 중복 헤더가 있으면 오류 발생
        # 대신 get_all_values()로 수동 처리
        all_values = self.worksheet.get_all_values()
        if not all_values:
            return []

        headers = all_values[0]
        data_rows = all_values[1:]

        result = []
        for row in data_rows:
            row_dict = {}
            for i, header in enumerate(headers):
                if header and i < len(row):
                    # 중복 헤더는 첫 번째 값만 사용
                    if header not in row_dict:
                        row_dict[header] = row[i]
            result.append(row_dict)

        return result

    def get_headers(self) -> List[str]:
        """헤더(첫 번째 행) 가져오기"""
        if not self.worksheet:
            raise Exception("워크시트가 연결되지 않았습니다.")

        if self._headers_cache is None:
            self._headers_cache = self.worksheet.row_values(1)
        return self._headers_cache

    def find_column_index(self, column_name: str) -> Optional[int]:
        """컬럼 이름으로 인덱스 찾기 (1-based)"""
        headers = self.get_headers()
        try:
            return headers.index(column_name) + 1
        except ValueError:
            return None

    def get_keywords_data(self) -> List[Dict]:
        """
        키워드 모니터링에 필요한 데이터 추출

        Returns:
            [
                {
                    'row': 2,
                    'cafe': '여우야',
                    'keyword': '송침유',
                    'keyword_views': 1000,
                    'post_url': 'https://cafe.naver.com/...',
                    'deleted': '',
                    'exposure_status': 'X',
                    'current_views': 500,
                    'priority': '4',
                    'publish_time': '2026-01-15',
                    'patrol_time': '2026-01-15 10:00:00',
                    'author_id': 'abc123'
                },
                ...
            ]
        """
        all_data = self.get_all_data()

        # 컬럼 매핑 (시트 컬럼명 -> 내부 키)
        column_mapping = {
            '카페': 'cafe',
            '키워드': 'keyword',
            '키워드조회수': 'keyword_views',
            'url': 'post_url',
            '삭제': 'deletion_status',
            '노출': 'exposure_status',
            '발행글조회수': 'current_views',
            '우선순위': 'priority',
            '발행시간': 'publish_time',
            '순찰시간': 'patrol_time',
            '발행아이디': 'author_id'
        }

        keywords_data = []
        for idx, row in enumerate(all_data, start=2):  # 2부터 시작 (헤더가 1)
            # 키워드가 없으면 건너뛰기
            keyword = row.get('키워드', '')
            if isinstance(keyword, str):
                keyword = keyword.strip()
            if not keyword:
                continue

            data = {'row': idx}
            for sheet_col, internal_key in column_mapping.items():
                data[internal_key] = row.get(sheet_col, '')

            keywords_data.append(data)

        return keywords_data

    def get_cafe_list(self) -> List[Dict]:
        """
        시트의 '카페' 컬럼에서 고유한 카페 목록 가져오기

        Returns:
            [
                {'cafe_name': '여우야', 'cafe_id': '여우야'},
                ...
            ]
        """
        all_data = self.get_all_data()

        cafe_set = set()
        for row in all_data:
            cafe = row.get('카페', '').strip()
            if cafe:
                cafe_set.add(cafe)

        return [{'cafe_name': cafe, 'cafe_id': cafe} for cafe in cafe_set]

    def update_cell(self, row: int, column_name: str, value):
        """
        특정 셀 업데이트

        Args:
            row: 행 번호 (1-based)
            column_name: 컬럼 이름
            value: 새 값
        """
        col_idx = self.find_column_index(column_name)
        if col_idx is None:
            print(f"경고: 컬럼 '{column_name}'을 찾을 수 없습니다.")
            return False

        try:
            self.worksheet.update_cell(row, col_idx, value)
            return True
        except Exception as e:
            print(f"셀 업데이트 실패 (행:{row}, 컬럼:{column_name}): {e}")
            return False

    def update_row(self, row: int, updates: Dict[str, any]):
        """
        특정 행의 여러 컬럼 업데이트

        Args:
            row: 행 번호 (1-based)
            updates: {컬럼명: 값} 딕셔너리
        """
        for column_name, value in updates.items():
            self.update_cell(row, column_name, value)
            time.sleep(0.1)  # API 레이트 리밋 방지

    def batch_update_cells(self, updates: List[Dict]):
        """
        여러 셀을 일괄 업데이트 (효율적)

        Args:
            updates: [{'row': 2, 'column': '노출 현황', 'value': '카페3'}, ...]
        """
        if not updates:
            return

        # gspread batch_update 형식으로 변환
        cell_updates = []

        for update in updates:
            row = update['row']
            col_idx = self.find_column_index(update['column'])
            if col_idx:
                cell_updates.append({
                    'range': gspread.utils.rowcol_to_a1(row, col_idx),
                    'values': [[update['value']]]
                })

        if cell_updates:
            try:
                self.worksheet.batch_update(cell_updates)
                print(f"{len(cell_updates)}개 셀 일괄 업데이트 완료")
            except Exception as e:
                print(f"일괄 업데이트 실패: {e}")

    def update_monitoring_result(self, row: int, exposure_status: str = None,
                                  top_cafe_url: str = None,
                                  top_author: str = None,
                                  views: int = None):
        """
        모니터링 결과 업데이트

        Args:
            row: 행 번호
            exposure_status: 노출 현황 (예: '카페3', '미노출')
            top_cafe_url: 최상단 카페 URL
            top_author: 최상단 작성자
            views: 조회수
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        updates = {
            '업데이트 날짜': current_time
        }

        if exposure_status is not None:
            updates['노출 현황'] = exposure_status

        if top_cafe_url is not None:
            updates['최상단 카페 URL'] = top_cafe_url

        if top_author is not None:
            updates['최상단'] = top_author

        if views is not None:
            updates['조회'] = views

        self.update_row(row, updates)

    def get_keywords_for_monitoring(self) -> List[Dict]:
        """
        모니터링할 키워드 목록 반환
        작성글url이 있는 키워드만 반환

        Returns:
            [
                {
                    'row': 2,
                    'keyword': '손가락 골절 깁스',
                    'target_url': 'https://cafe.naver.com/...',
                    'priority': '최상',
                    'author_id': 'njfe840155'
                },
                ...
            ]
        """
        keywords_data = self.get_keywords_data()

        monitoring_list = []
        for data in keywords_data:
            post_url = data.get('post_url', '')
            if isinstance(post_url, str):
                post_url = post_url.strip()
            if not post_url:
                continue

            monitoring_list.append({
                'row': data['row'],
                'keyword': data['keyword'],
                'target_url': post_url,
                'priority': data.get('priority', ''),
                'current_status': data.get('exposure_status', ''),
                'author_id': data.get('author_id', ''),
                'is_deleted': data.get('deletion_status', '')
            })

        return monitoring_list

    def batch_update_monitoring_results(self, results: List[Dict]):
        """
        여러 키워드의 모니터링 결과를 일괄 업데이트

        Args:
            results: [
                {
                    'row': 2,
                    'exposure_status': 'O' 또는 'X' 또는 순위,
                },
                ...
            ]
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        updates = []
        for result in results:
            row = result['row']

            # 순찰시간 업데이트
            updates.append({'row': row, 'column': '순찰시간', 'value': current_time})

            # 노출 상태 업데이트
            if 'exposure_status' in result:
                updates.append({'row': row, 'column': '노출', 'value': result['exposure_status']})
            # 삭제 여부 업데이트
            if 'deletion_status' in result:
                updates.append({'row': row, 'column': '삭제', 'value': result['deletion_status']})

        self.batch_update_cells(updates)
