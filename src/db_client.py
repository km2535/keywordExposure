"""
MySQL DB 연동 모듈
- 키워드 데이터 읽기
- 모니터링 결과 업데이트
"""

import pymysql
import logging
from datetime import datetime
from typing import List, Dict, Optional


class DatabaseClient:
    """MySQL 데이터베이스 클라이언트"""

    def __init__(self, host: str, port: int, user: str, password: str,
                 database: str, table: str = 'keyword_patrol_logs'):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.table = table
        self.connection = None

    def connect(self) -> bool:
        """DB 연결"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                autocommit=False
            )
            logging.info(f"DB 연결 성공: {self.database}@{self.host}")
            return True
        except Exception as e:
            logging.error(f"DB 연결 실패: {e}")
            return False

    def disconnect(self):
        """DB 연결 해제"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def _ensure_connection(self) -> bool:
        """연결 상태 확인 및 재연결"""
        try:
            if self.connection and self.connection.open:
                self.connection.ping(reconnect=True)
                return True
            return self.connect()
        except Exception:
            return self.connect()

    def get_keywords_for_monitoring(self) -> List[Dict]:
        """
        모니터링할 키워드 목록을 DB에서 가져오기
        keywords 테이블과 JOIN하여 키워드 텍스트 포함

        Returns:
            [
                {
                    'row': 1,                          # DB id (행 식별자)
                    'keyword': '손가락 골절 깁스',
                    'target_url': 'https://...',       # result_url
                    'current_status': 'O' or 'X',      # is_exposed
                    'author_id': 'njfe840155',         # account_id
                    'is_deleted': 'O' or 'X'           # is_deleted
                },
                ...
            ]
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 키워드를 가져올 수 없습니다.")
            return []

        sql = f"""
            SELECT
                kr.id,
                k.keyword,
                kr.result_url,
                kr.is_deleted,
                kr.is_exposed,
                kr.account_id
            FROM {self.table} kr
            JOIN keywords k ON kr.keyword_id = k.keyword_id
            ORDER BY kr.id
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall()

            result = []
            for row in rows:
                db_id, keyword, result_url, is_deleted, is_exposed, account_id = row
                result.append({
                    'row': db_id,
                    'keyword': keyword or '',
                    'target_url': result_url or '',
                    'current_status': 'O' if is_exposed else 'X',
                    'author_id': account_id or '',
                    'is_deleted': 'O' if is_deleted else 'X',
                })

            logging.info(f"DB에서 키워드 {len(result)}개 로드 완료")
            return result

        except Exception as e:
            logging.error(f"키워드 로드 실패: {e}")
            return []

    def mark_rows_deleted(self, db_ids: List[int]):
        """삭제 확인된 행들을 DB에서 is_deleted=1로 업데이트"""
        if not db_ids:
            return

        if not self._ensure_connection():
            logging.error("DB 연결 실패로 삭제 업데이트를 건너뜁니다.")
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        placeholders = ', '.join(['%s'] * len(db_ids))

        sql = f"""
            UPDATE {self.table}
            SET is_deleted = 1, updated_at = %s
            WHERE id IN ({placeholders})
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, [current_time] + db_ids)
            self.connection.commit()
            logging.info(f"삭제 처리 {len(db_ids)}개 업데이트 완료")
        except Exception as e:
            self.connection.rollback()
            logging.error(f"삭제 업데이트 실패: {e}")

    def batch_update_monitoring_results(self, results: List[Dict]):
        """
        모니터링 결과를 DB에 일괄 업데이트
        google_sheets.batch_update_monitoring_results와 동일한 results 형식 사용

        Args:
            results: [
                {
                    'url': 'https://cafe.naver.com/...',   # result_url (WHERE 조건)
                    'exposure_status': 'O' or 'X',         # is_exposed
                    'deletion_status': 'O' or 'X',         # is_deleted
                    'rank': 3 or None,                     # rank
                    'popular_status': 'O' or 'X',          # is_popular
                    'cross_keywords': ['키워드1(1)', ...],  # is_cross_exposed + cross_keyword1~5
                },
                ...
            ]
        """
        if not results:
            return

        if not self._ensure_connection():
            logging.error("DB 연결 실패로 업데이트를 건너뜁니다.")
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated_count = 0

        try:
            with self.connection.cursor() as cursor:
                for result in results:
                    url = result.get('url', '').strip()
                    if not url:
                        continue

                    set_clauses = ['checked_at = %s', 'updated_at = %s']
                    params = [current_time, current_time]

                    # 노출 여부 (O→1, X→0)
                    if 'exposure_status' in result:
                        set_clauses.append('is_exposed = %s')
                        params.append(1 if result['exposure_status'] == 'O' else 0)

                    # 순위 (None이면 NULL)
                    if 'rank' in result:
                        set_clauses.append('rank = %s')
                        params.append(result['rank'])  # None → NULL

                    # 삭제 여부 (O→1, X→0)
                    if 'deletion_status' in result:
                        set_clauses.append('is_deleted = %s')
                        params.append(1 if result['deletion_status'] == 'O' else 0)

                    # 인기글 여부 (O→1, X→0)
                    if 'popular_status' in result:
                        set_clauses.append('is_popular = %s')
                        params.append(1 if result['popular_status'] == 'O' else 0)

                    # 교차노출 (cross_keywords 리스트 기반)
                    if 'cross_keywords' in result:
                        cross_kws = result['cross_keywords']
                        set_clauses.append('is_cross_exposed = %s')
                        params.append(1 if cross_kws else 0)

                        # 교차키워드1~5
                        for i in range(1, 6):
                            set_clauses.append(f'cross_keyword{i} = %s')
                            params.append(cross_kws[i - 1] if i <= len(cross_kws) else None)

                    params.append(url)  # WHERE 절

                    sql = f"""
                        UPDATE {self.table}
                        SET {', '.join(set_clauses)}
                        WHERE result_url = %s
                    """
                    cursor.execute(sql, params)
                    updated_count += cursor.rowcount

            self.connection.commit()
            logging.info(f"DB {updated_count}개 행 업데이트 완료 (처리 대상: {len(results)}개)")

        except Exception as e:
            self.connection.rollback()
            logging.error(f"DB 배치 업데이트 실패: {e}")

    def get_all_patrol_logs(self):
        """
        keyword_patrol_logs 전체 데이터를 Google Sheets(키워드순찰 시트)에 쓸 수 있는 2D 배열로 반환

        시트 헤더 순서:
        카페 / 키워드 / 조회수 / url / 삭제 / 노출 / 순위 / 교차노출 /
        교차키워드1~5 / 발행시간 / 순찰시간 / 발행아이디 / 제품 / 댓글묶음 / (빈열) / 인기글여부

        Returns:
            (headers, rows) 튜플
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 patrol_logs를 가져올 수 없습니다.")
            return [], []

        sql = f"""
            SELECT
                kr.cafe_name,
                k.keyword,
                k.search_volume,
                kr.result_url,
                kr.is_deleted,
                kr.is_exposed,
                kr.rank,
                kr.is_cross_exposed,
                kr.cross_keyword1,
                kr.cross_keyword2,
                kr.cross_keyword3,
                kr.cross_keyword4,
                kr.cross_keyword5,
                kr.published_at,
                kr.checked_at,
                kr.account_id,
                kr.product,
                kr.comment_group,
                kr.is_popular,
                kr.updated_at
            FROM {self.table} kr
            JOIN keywords k ON kr.keyword_id = k.keyword_id
            ORDER BY kr.id
        """

        headers = [
            '카페', '키워드', '조회수', 'url',
            '삭제', '노출', '순위', '교차노출',
            '교차키워드1', '교차키워드2', '교차키워드3', '교차키워드4', '교차키워드5',
            '발행시간', '순찰시간', '발행아이디', '제품', '댓글묶음', '인기글여부', '업데이트시간'
        ]

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                raw_rows = cursor.fetchall()

            rows = []
            for raw in raw_rows:
                (cafe_name, keyword, search_volume, result_url,
                 is_deleted, is_exposed, rank, is_cross_exposed,
                 cross_kw1, cross_kw2, cross_kw3, cross_kw4, cross_kw5,
                 published_at, checked_at, account_id,
                 product, comment_group, is_popular, updated_at) = raw

                rows.append([
                    cafe_name or '',
                    keyword or '',
                    search_volume if search_volume is not None else '',
                    result_url or '',
                    'O' if is_deleted else 'X',
                    'O' if is_exposed else 'X',
                    rank if rank is not None else '',
                    'O' if is_cross_exposed else 'X',
                    cross_kw1 or '',
                    cross_kw2 or '',
                    cross_kw3 or '',
                    cross_kw4 or '',
                    cross_kw5 or '',
                    str(published_at) if published_at else '',
                    str(checked_at) if checked_at else '',
                    account_id or '',
                    product or '',
                    comment_group or '',
                    'O' if is_popular else 'X',   # S열
                    str(updated_at) if updated_at else '',  # T열
                ])

            logging.info(f"patrol_logs {len(rows)}개 행 로드 완료")
            return headers, rows

        except Exception as e:
            logging.error(f"patrol_logs 로드 실패: {e}")
            return [], []


    def get_keyword_list_from_view(self):
        """
        keyword_list_view 전체 데이터를 Google Sheets(키워드목록 시트)에 쓸 수 있는 2D 배열로 반환

        시트 헤더 순서:
        키워드 / 키워드조회수 / 제품 / 삭제 / 노출 / 순위 / 교차노출 /
        카페 / 발행시간 / 카페(url) / 인기글여부 / 교차키워드1~5

        Returns:
            (headers, rows) 튜플
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 keyword_list_view를 가져올 수 없습니다.")
            return [], []

        sql = """
            SELECT
                `키워드`,
                `키워드조회수`,
                `제품`,
                `삭제`,
                `노출`,
                `순위`,
                `교차노출`,
                `카페`,
                `발행시간`,
                `카페url`,
                `인기글여부`,
                `교차키워드1`,
                `교차키워드2`,
                `교차키워드3`,
                `교차키워드4`,
                `교차키워드5`
            FROM cafe_auto.keyword_list_view
            ORDER BY `키워드조회수` DESC
        """

        # 시트 헤더 (두 번째 '카페' 열은 카페url 내용을 담음)
        headers = [
            '키워드', '키워드조회수', '제품',
            '삭제', '노출', '순위', '교차노출',
            '카페', '발행시간', '카페',
            '인기글여부',
            '교차키워드1', '교차키워드2', '교차키워드3', '교차키워드4', '교차키워드5'
        ]

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                raw_rows = cursor.fetchall()

            rows = []
            for raw in raw_rows:
                (keyword, search_volume, product,
                 is_deleted, is_exposed, rank, is_cross_exposed,
                 cafe_name, published_at, cafe_url,
                 is_popular,
                 cross_kw1, cross_kw2, cross_kw3, cross_kw4, cross_kw5) = raw

                rows.append([
                    keyword or '',
                    search_volume if search_volume is not None else '',
                    product or '',
                    'O' if is_deleted else 'X',
                    'O' if is_exposed else 'X',
                    rank if rank is not None else '',
                    'O' if is_cross_exposed else 'X',
                    cafe_name or '',
                    str(published_at) if published_at else '',
                    cafe_url or '',
                    'O' if is_popular else 'X',
                    cross_kw1 or '',
                    cross_kw2 or '',
                    cross_kw3 or '',
                    cross_kw4 or '',
                    cross_kw5 or '',
                ])

            logging.info(f"keyword_list_view {len(rows)}개 행 로드 완료")
            return headers, rows

        except Exception as e:
            logging.error(f"keyword_list_view 로드 실패: {e}")
            return [], []
