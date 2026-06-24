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

    def get_keywords_for_monitoring(self, products: Optional[List[str]] = None) -> List[Dict]:
        """
        모니터링할 키워드 목록을 DB에서 가져오기
        keywords 테이블과 JOIN하여 키워드 텍스트 포함

        Args:
            products: 필터링할 제품 목록 (예: ['cancer', 'diabetes']). None이면 전체.

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

        where_clause = ""
        params = []
        if products:
            placeholders = ', '.join(['%s'] * len(products))
            where_clause = f"WHERE kr.product IN ({placeholders})"
            params = list(products)

        sql = f"""
            SELECT
                kr.id,
                k.keyword_id,
                k.keyword,
                kr.result_url,
                kr.is_deleted,
                kr.is_exposed,
                kr.account_id
            FROM {self.table} kr
            JOIN keywords k ON kr.keyword_id = k.keyword_id
            {where_clause}
            ORDER BY kr.id
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()

            result = []
            for row in rows:
                db_id, keyword_id, keyword, result_url, is_deleted, is_exposed, account_id = row
                result.append({
                    'row': db_id,
                    'keyword_id': keyword_id,
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

    def get_distinct_products(self) -> List[str]:
        """keyword_patrol_logs 테이블에서 product 고유값 목록 반환"""
        if not self._ensure_connection():
            return []
        sql = f"SELECT DISTINCT product FROM {self.table} WHERE product IS NOT NULL AND product != '' ORDER BY product"
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"제품 목록 조회 실패: {e}")
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
                    row_id = result.get('row')
                    if not url and not row_id:
                        continue

                    set_clauses = ['updated_at = %s']
                    params = [current_time]

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
                        set_clauses.append('checked_at = %s')
                        params.append(current_time)
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

                    # 레이아웃 정보: 블록 위치 (head/body/None)
                    if 'block_position' in result:
                        set_clauses.append('block_position = %s')
                        params.append(result['block_position'])  # None → NULL

                    # 레이아웃 정보: 글 Y위치 % (None → NULL)
                    if 'post_y_pct' in result:
                        set_clauses.append('post_y_pct = %s')
                        params.append(result['post_y_pct'])

                    if url:
                        params.append(url)
                        sql = f"""
                            UPDATE {self.table}
                            SET {', '.join(set_clauses)}
                            WHERE result_url = %s
                        """
                    else:
                        params.append(row_id)
                        sql = f"""
                            UPDATE {self.table}
                            SET {', '.join(set_clauses)}
                            WHERE id = %s
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
            WHERE kr.result_url IS NOT NULL AND kr.result_url != ''
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
                `비대표카페노출여부`,
                `교차키워드1`,
                `교차키워드2`,
                `교차키워드3`,
                `교차키워드4`,
                `교차키워드5`,
                `상하단구분`,
                `첫카페글위치`,
                `블록위치`,
                `글위치`
            FROM cafe_auto.keyword_list_view
            ORDER BY `키워드조회수` DESC
        """

        # 시트 헤더 (두 번째 '카페' 열은 카페url 내용을 담음, 레이아웃 컬럼 4개 추가)
        headers = [
            '키워드', '키워드조회수', '제품',
            '삭제', '노출', '순위', '교차노출',
            '카페', '발행시간', '카페',
            '인기글여부', '비대표카페노출여부',
            '교차키워드1', '교차키워드2', '교차키워드3', '교차키워드4', '교차키워드5',
            '상하단구분', '첫카페글위치', '블록위치', '글위치'
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
                 is_popular, non_main_cafe_exposed,
                 cross_kw1, cross_kw2, cross_kw3, cross_kw4, cross_kw5,
                 has_split_block, first_cafe_y_pct, block_position, post_y_pct) = raw

                rows.append([
                    keyword or '',
                    search_volume if search_volume is not None else '',
                    product or '',
                    'O' if is_deleted else 'X',
                    'O' if is_exposed else 'X',
                    rank if rank is not None else '',
                    'O' if is_cross_exposed else 'X',
                    cafe_name or '',
                    published_at.strftime('%Y-%m-%d') if published_at else '',
                    cafe_url or '',
                    'O' if is_popular else 'X',
                    non_main_cafe_exposed or '',
                    cross_kw1 or '',
                    cross_kw2 or '',
                    cross_kw3 or '',
                    cross_kw4 or '',
                    cross_kw5 or '',
                    'O' if has_split_block else ('X' if has_split_block is not None else ''),
                    str(round(float(first_cafe_y_pct), 1)) + '%' if first_cafe_y_pct is not None else '',
                    {'head': '상단', 'body': '하단', 'single': '단일'}.get(block_position, '') if block_position else '',
                    str(round(float(post_y_pct), 1)) + '%' if post_y_pct is not None else '',
                ])

            logging.info(f"keyword_list_view {len(rows)}개 행 로드 완료")
            return headers, rows

        except Exception as e:
            logging.error(f"keyword_list_view 로드 실패: {e}")
            return [], []

    def upsert_main_cafe_status(self, keyword_id: int, is_main_cafe: bool):
        """
        keyword_main_cafe 테이블에 대표카페 여부 upsert.
        이미 존재하면 UPDATE, 없으면 INSERT.
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 대표카페 업데이트를 건너뜁니다.")
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            INSERT INTO keyword_main_cafe (keyword_id, is_main_cafe, updated_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                is_main_cafe = VALUES(is_main_cafe),
                updated_at   = VALUES(updated_at)
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, (keyword_id, 1 if is_main_cafe else 0, current_time))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            logging.error(f"대표카페 upsert 실패 (keyword_id={keyword_id}): {e}")

    def upsert_layout_info(self, keyword_id: int, layout: dict):
        """
        keyword_layout_info 테이블에 레이아웃 측정값 upsert.
        이미 존재하면 UPDATE, 없으면 INSERT.

        Args:
            keyword_id: keywords.keyword_id
            layout: {
                'has_split_block': bool or None,
                'first_cafe_y_pct': float or None,
            }

        NOTE: Phase 1 DDL (DB에서 직접 실행 필요):
        CREATE TABLE keyword_layout_info (
            keyword_id INT NOT NULL PRIMARY KEY,
            has_split_block TINYINT(1) DEFAULT NULL,
            first_cafe_y_pct DECIMAL(5,2) DEFAULT NULL,
            updated_at DATETIME DEFAULT NULL,
            CONSTRAINT fk_layout_keyword FOREIGN KEY (keyword_id) REFERENCES keywords (keyword_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        ALTER TABLE keyword_patrol_logs
            ADD COLUMN block_position ENUM('head','body') DEFAULT NULL,
            ADD COLUMN post_y_pct DECIMAL(5,2) DEFAULT NULL;
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 레이아웃 정보 업데이트를 건너뜁니다.")
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        has_split_block = layout.get('has_split_block')
        first_cafe_y_pct = layout.get('first_cafe_y_pct')

        sql = """
            INSERT INTO keyword_layout_info (keyword_id, has_split_block, first_cafe_y_pct, updated_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                has_split_block   = COALESCE(VALUES(has_split_block), has_split_block),
                first_cafe_y_pct  = COALESCE(VALUES(first_cafe_y_pct), first_cafe_y_pct),
                updated_at        = VALUES(updated_at)
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, (keyword_id, has_split_block, first_cafe_y_pct, current_time))
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            logging.error(f"레이아웃 정보 upsert 실패 (keyword_id={keyword_id}): {e}")

    # ===================================== 블로그 순찰 메서드 =====================================

    def get_blog_posts_for_monitoring(self, products: Optional[List[str]] = None) -> List[Dict]:
        """
        블로그 순찰 대상 blog_post 목록을 DB에서 가져오기
        blog_post 테이블과 keywords 테이블을 JOIN하여 키워드 텍스트 포함

        Args:
            products: 필터링할 제품 목록 (예: ['cancer', 'diabetes']). None이면 전체.

        Returns:
            [
                {
                    'row': 1,
                    'keyword': '탈모 샴푸 추천',
                    'target_url': 'https://blog.naver.com/xxx/123',
                    'current_status': 'O' or 'X',
                    'author_id': 'blogger_id',
                },
                ...
            ]
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 블로그 포스트를 가져올 수 없습니다.")
            return []

        where_clause = ""
        params = []
        if products:
            placeholders = ', '.join(['%s'] * len(products))
            where_clause = f"WHERE bp.product IN ({placeholders})"
            params = list(products)

        sql = f"""
            SELECT
                bp.id,
                k.keyword,
                bp.result_url,
                bp.is_exposed,
                bp.account_id,
                bp.is_deleted
            FROM blog_post bp
            JOIN keywords k ON bp.keyword_id = k.keyword_id
            {where_clause}
            ORDER BY bp.id
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()

            result = []
            for row in rows:
                db_id, keyword, result_url, is_exposed, account_id, is_deleted = row
                result.append({
                    'row': db_id,
                    'keyword': keyword or '',
                    'target_url': result_url or '',
                    'current_status': 'O' if is_exposed else 'X',
                    'author_id': account_id or '',
                    'is_deleted': bool(is_deleted),
                })

            logging.info(f"DB에서 블로그 포스트 {len(result)}개 로드 완료")
            return result

        except Exception as e:
            logging.error(f"블로그 포스트 로드 실패: {e}")
            return []

    def batch_update_blog_results(self, results: List[Dict]):
        """
        블로그 순찰 결과를 blog_post 테이블에 일괄 업데이트
        batch_update_monitoring_results()와 동일한 결과 구조 사용
        단, is_deleted / deletion_status 관련 처리는 제외

        Args:
            results: [
                {
                    'url': 'https://blog.naver.com/...',   # result_url (WHERE 조건)
                    'exposure_status': 'O' or 'X',         # is_exposed
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
            logging.error("DB 연결 실패로 블로그 업데이트를 건너뜁니다.")
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated_count = 0

        try:
            with self.connection.cursor() as cursor:
                for result in results:
                    url = result.get('url', '').strip()
                    row_id = result.get('row')
                    if not url and not row_id:
                        continue

                    set_clauses = ['updated_at = %s', 'checked_at = %s']
                    params = [current_time, current_time]

                    # 노출 여부 (O→1, X→0)
                    if 'exposure_status' in result:
                        set_clauses.append('is_exposed = %s')
                        params.append(1 if result['exposure_status'] == 'O' else 0)

                    # 순위 (None이면 NULL)
                    if 'rank' in result:
                        set_clauses.append('rank = %s')
                        params.append(result['rank'])

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

                    if url:
                        params.append(url)
                        sql = f"""
                            UPDATE blog_post
                            SET {', '.join(set_clauses)}
                            WHERE result_url = %s
                        """
                    else:
                        params.append(row_id)
                        sql = f"""
                            UPDATE blog_post
                            SET {', '.join(set_clauses)}
                            WHERE id = %s
                        """
                    cursor.execute(sql, params)
                    updated_count += cursor.rowcount

            self.connection.commit()
            logging.info(f"블로그 DB {updated_count}개 행 업데이트 완료 (처리 대상: {len(results)}개)")

        except Exception as e:
            self.connection.rollback()
            logging.error(f"블로그 DB 배치 업데이트 실패: {e}")

    def get_all_blog_patrol_logs(self):
        """
        blog_post 전체 데이터를 Google Sheets(블로그순찰 시트)에 쓸 수 있는 2D 배열로 반환

        시트 헤더 순서:
        블로그 / 키워드 / 조회수 / url / 노출 / 순위 / 교차노출 /
        교차키워드1~5 / 발행시간 / 순찰시간 / 발행아이디 / 제품 / 인기글여부 / 업데이트시간

        Returns:
            (headers, rows) 튜플
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 블로그 patrol_logs를 가져올 수 없습니다.")
            return [], []

        sql = """
            SELECT
                k.keyword,
                k.search_volume,
                bp.result_url,
                bp.is_deleted,
                bp.is_exposed,
                bp.rank,
                bp.is_cross_exposed,
                bp.cross_keyword1,
                bp.cross_keyword2,
                bp.cross_keyword3,
                bp.cross_keyword4,
                bp.cross_keyword5,
                bp.published_at,
                bp.checked_at,
                bp.account_id,
                bp.product,
                bp.is_popular,
                bp.updated_at
            FROM blog_post bp
            JOIN keywords k ON bp.keyword_id = k.keyword_id
            WHERE bp.result_url IS NOT NULL AND bp.result_url != ''
            ORDER BY bp.id
        """

        headers = [
            '키워드', '조회수', 'url',
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
                (keyword, search_volume, result_url,
                 is_deleted, is_exposed, rank, is_cross_exposed,
                 cross_kw1, cross_kw2, cross_kw3, cross_kw4, cross_kw5,
                 published_at, checked_at, account_id,
                 product, is_popular, updated_at) = raw

                rows.append([
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
                    '',  # 댓글묶음 (DB 컬럼 없음)
                    'O' if is_popular else 'X',
                    str(updated_at) if updated_at else '',
                ])

            logging.info(f"블로그 patrol_logs {len(rows)}개 행 로드 완료")
            return headers, rows

        except Exception as e:
            logging.error(f"블로그 patrol_logs 로드 실패: {e}")
            return [], []

    def get_blog_keyword_list_from_view(self):
        """
        blog_post_list_view 전체 데이터를 Google Sheets(블로그 키워드목록 시트)에 쓸 수 있는 2D 배열로 반환

        Returns:
            (headers, rows) 튜플
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 blog_post_list_view를 가져올 수 없습니다.")
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
                `발행시간`,
                `블로그url`,
                `인기글여부`,
                `교차키워드1`,
                `교차키워드2`,
                `교차키워드3`,
                `교차키워드4`,
                `교차키워드5`
            FROM cafe_auto.blog_post_list_view
            ORDER BY `키워드조회수` DESC
        """

        headers = [
            '키워드', '키워드조회수', '제품',
            '삭제', '노출', '순위', '교차노출',
            '발행시간', 'url', '인기글여부',
            '교차키워드1', '교차키워드2', '교차키워드3', '교차키워드4', '교차키워드5',
        ]

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                raw_rows = cursor.fetchall()

            rows = []
            for raw in raw_rows:
                (keyword, search_volume, product,
                 is_deleted, is_exposed, rank, is_cross_exposed,
                 published_at, blog_url, is_popular,
                 cross_kw1, cross_kw2, cross_kw3, cross_kw4, cross_kw5) = raw

                rows.append([
                    keyword or '',
                    search_volume if search_volume is not None else '',
                    product or '',
                    'O' if is_deleted else 'X',
                    'O' if is_exposed else 'X',
                    rank if rank is not None else '',
                    'O' if is_cross_exposed else 'X',
                    str(published_at) if published_at else '',
                    blog_url or '',
                    'O' if is_popular else 'X',
                    cross_kw1 or '',
                    cross_kw2 or '',
                    cross_kw3 or '',
                    cross_kw4 or '',
                    cross_kw5 or '',
                ])

            logging.info(f"blog_post_list_view {len(rows)}개 행 로드 완료")
            return headers, rows

        except Exception as e:
            logging.error(f"blog_post_list_view 로드 실패: {e}")
            return [], []

    def get_keywords_for_ranking_analysis(self, products: Optional[List[str]] = None) -> List[Dict]:
        """
        레이아웃 분석 대상 키워드 목록 반환 (keyword_id + keyword).
        keyword_patrol_logs에 등록된 키워드 기준.
        """
        if not self._ensure_connection():
            return []

        where_clause = ""
        params = []
        if products:
            placeholders = ', '.join(['%s'] * len(products))
            where_clause = f"WHERE kr.product IN ({placeholders})"
            params = list(products)

        sql = f"""
            SELECT DISTINCT k.keyword_id, k.keyword
            FROM keywords k
            JOIN {self.table} kr ON k.keyword_id = kr.keyword_id
            {where_clause}
            ORDER BY k.keyword
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, params)
                return [{'keyword_id': r[0], 'keyword': r[1]} for r in cursor.fetchall()]
        except Exception as e:
            logging.error(f"랭킹 분석 키워드 목록 조회 실패: {e}")
            return []

    def replace_cafe_ranking(self, keyword_id: int, has_split_block: bool,
                             main_results: list, popular_results: list):
        """
        keyword_cafe_ranking 테이블에 해당 keyword_id 데이터를 DELETE 후 INSERT.

        DDL (DB에서 직접 실행 필요):
        CREATE TABLE keyword_cafe_ranking (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            keyword_id    INT NOT NULL,
            section       ENUM('main','popular') NOT NULL DEFAULT 'main',
            rank          INT NOT NULL,
            cafe_name     VARCHAR(500),
            result_url    VARCHAR(1000),
            block_type    ENUM('head','body','single') NOT NULL DEFAULT 'single',
            has_split_block TINYINT(1) NOT NULL DEFAULT 0,
            updated_at    DATETIME,
            UNIQUE KEY uq_ranking (keyword_id, section, rank),
            CONSTRAINT fk_ranking_keyword FOREIGN KEY (keyword_id) REFERENCES keywords (keyword_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        Args:
            keyword_id:    keywords.keyword_id
            has_split_block: 상하단 구분 여부
            main_results:  [{'rank': 1, 'cafe_name': '...', 'url': '...', 'block': 'head'|'body'|'single'}, ...]
            popular_results: [{'rank': 1, 'cafe_name': '...', 'url': '...'}, ...]
        """
        if not self._ensure_connection():
            logging.error("DB 연결 실패로 카페 랭킹 업데이트를 건너뜁니다.")
            return

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM keyword_cafe_ranking WHERE keyword_id = %s",
                    (keyword_id,)
                )
                rows = []
                for r in main_results:
                    block_type = r.get('block', 'single') if has_split_block else 'single'
                    rows.append((keyword_id, 'main', r['rank'],
                                 r.get('cafe_name'), r.get('display_name'),
                                 r.get('url'), block_type,
                                 r.get('published_at') or None,
                                 1 if has_split_block else 0,
                                 current_time))
                for r in popular_results:
                    rows.append((keyword_id, 'popular', r['rank'],
                                 r.get('cafe_name'), r.get('display_name'),
                                 r.get('url'), 'single',
                                 r.get('published_at') or None,
                                 1 if has_split_block else 0,
                                 current_time))
                if rows:
                    cursor.executemany("""
                        INSERT INTO keyword_cafe_ranking
                            (keyword_id, section, rank, cafe_name, display_name,
                             result_url, block_type, published_at, has_split_block, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, rows)
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            logging.error(f"카페 랭킹 저장 실패 (keyword_id={keyword_id}): {e}")

    def get_cafe_ranking_for_sheet(self, max_main_rank: int = 8,
                                   max_popular_rank: int = 5):
        """
        keyword_cafe_ranking 전체 데이터를 Google Sheets에 쓸 수 있는 2D 배열로 반환.

        시트 헤더:
        키워드 | 레이아웃 | 1위~N위 (메인) | 인기글1~M위

        셀 값:
        - 상하단 구분: "카페명(상단)" / "카페명(하단)"
        - 단일: "카페명"
        - 없음: ""

        Returns:
            (headers, rows) 튜플
        """
        if not self._ensure_connection():
            return [], []

        sql = """
            SELECT
                k.keyword,
                kcr.section,
                kcr.rank,
                kcr.cafe_name,
                kcr.display_name,
                kcr.block_type,
                kcr.published_at,
                kcr.has_split_block
            FROM keyword_cafe_ranking kcr
            JOIN keywords k ON kcr.keyword_id = k.keyword_id
            ORDER BY k.keyword, kcr.section, kcr.rank
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                raw = cursor.fetchall()
        except Exception as e:
            logging.error(f"카페 랭킹 조회 실패: {e}")
            return [], []

        from collections import defaultdict
        grouped = defaultdict(lambda: {'has_split': False, 'main': {}, 'popular': {}})
        for keyword, section, rank, cafe_name, display_name, block_type, published_at, has_split_block in raw:
            grouped[keyword]['has_split'] = bool(has_split_block)
            name = display_name or cafe_name or ''
            if section == 'main':
                grouped[keyword]['main'][rank] = (name, block_type, published_at)
            else:
                grouped[keyword]['popular'][rank] = (name, published_at)

        block_label = {'head': '상단', 'body': '하단', 'single': ''}

        headers = (['키워드', '레이아웃'] +
                   [f'{i}위' for i in range(1, max_main_rank + 1)] +
                   [f'인기글{i}위' for i in range(1, max_popular_rank + 1)])

        rows = []
        for keyword in sorted(grouped.keys()):
            data = grouped[keyword]
            layout = '상하단구분' if data['has_split'] else '단일'
            row = [keyword, layout]

            for i in range(1, max_main_rank + 1):
                if i in data['main']:
                    name, block_type, published_at = data['main'][i]
                    label = block_label.get(block_type, '')
                    # 예: 컬처블룸(상단) 2026.02.03
                    cell = name
                    if label:
                        cell += f'({label})'
                    if published_at:
                        cell += f' {published_at}'
                else:
                    cell = ''
                row.append(cell)

            for i in range(1, max_popular_rank + 1):
                if i in data['popular']:
                    name, published_at = data['popular'][i]
                    cell = f'{name} {published_at}' if published_at else name
                else:
                    cell = ''
                row.append(cell)

            rows.append(row)

        logging.info(f"카페 랭킹 시트 데이터 {len(rows)}개 키워드 준비 완료")
        return headers, rows

    def get_distinct_blog_products(self) -> List[str]:
        """blog_post 테이블에서 product 고유값 목록 반환 (GUI 제품 드롭다운용)"""
        if not self._ensure_connection():
            return []
        sql = "SELECT DISTINCT product FROM blog_post WHERE product IS NOT NULL AND product != '' ORDER BY product"
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"블로그 제품 목록 조회 실패: {e}")
            return []
