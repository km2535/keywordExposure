# 레이아웃 측정 기능 구현 완료

**구현 일자**: 2026-06-24
**구현 범위**: Phase 2, 3, 4 (DB DDL 제외)
**상태**: ✓ 완료

---

## 구현 개요

네이버 검색결과 페이지의 레이아웃 구조를 측정하는 기능을 추가했습니다. 키워드당 1회 Selenium 호출로 모든 URL의 위치를 측정하는 최적화 설계를 적용했습니다.

### 측정 항목

- **키워드 단위** (keyword_layout_info):
  - `has_split_block`: 상하단 블록 분리 여부 (\_fsolid_head 존재 여부)
  - `first_cafe_y_pct`: 첫 카페글 Y위치 (scrollHeight 대비 %)

- **글 단위** (keyword_patrol_logs):
  - `block_position`: 글이 속한 블록 ('head' / 'body' / NULL)
  - `post_y_pct`: 글 Y위치 % (scrollHeight 대비)

---

## Phase 2: src/scraper.py — get_layout_metrics() 추가

### 메서드 시그니처

```python
def get_layout_metrics(self, keyword: str, target_urls: list = None) -> dict
```

### 반환값

```python
{
    'has_split_block': bool or None,
    'first_cafe_y_pct': float or None,
    'url_metrics': {
        'https://cafe.naver.com/xxx/123': {
            'block_position': 'head' or 'body' or None,
            'post_y_pct': float or None,
        },
        ...
    }
}
```

### 구현 내용

1. Selenium 드라이버로 네이버 검색결과 페이지 로딩
2. 페이지 높이(scrollHeight) 확인 후 계산 기준으로 사용
3. JavaScript로 한 번에 모든 요소 측정:
   - `_fsolid_head` 클래스 존재 여부 확인 → `has_split_block`
   - 첫 카페글 Y위치 측정 → `first_cafe_y_pct`
   - target_urls의 각 링크 위치 및 블록 위치 측정 → `url_metrics`
4. 실패 시 모두 None 반환, 예외는 로그에만 기록 (순찰 루프 중단 없음)

### 주요 특징

- **JavaScript 최적화**: 모든 측정을 한 번의 스크립트 실행으로 처리
- **URL 정규화**: 쿼리스트링과 JWT 토큰 제거 후 비교
- **블록 판정**: 요소의 상위 요소(ancestor) 순회로 `_fsolid_head`/`_fsolid_body` 판정
- **오류 격리**: 레이아웃 측정 실패가 기존 순찰 기능을 방해하지 않음

---

## Phase 3: src/db_client.py 수정

### 3-1. `upsert_layout_info()` 신규 추가

```python
def upsert_layout_info(self, keyword_id: int, layout: dict)
```

- `keyword_layout_info` 테이블에 키워드 단위 레이아웃 정보 저장
- INSERT ... ON DUPLICATE KEY UPDATE 방식으로 upsert
- None 값은 `COALESCE()`로 기존 값 유지

**필요한 DDL**:
```sql
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
```

### 3-2. `batch_update_monitoring_results()` 확장

기존 메서드에 글 단위 레이아웃 정보 처리 로직 추가:

```python
# 레이아웃 정보: 블록 위치 (head/body/None)
if 'block_position' in result:
    set_clauses.append('block_position = %s')
    params.append(result['block_position'])

# 레이아웃 정보: 글 Y위치 % (None → NULL)
if 'post_y_pct' in result:
    set_clauses.append('post_y_pct = %s')
    params.append(result['post_y_pct'])
```

- 키가 없으면 무시 (하위 호환성 유지)
- None 값은 자동으로 NULL로 변환됨

### 3-3. `get_keyword_list_from_view()` 확장

SQL에 4개 컬럼 추가:
```sql
`상하단구분`,
`첫카페글위치`,
`블록위치`,
`글위치`
```

헤더와 rows 처리 로직에 대응:
- `상하단구분`: 'O' (True) / 'X' (False) / '' (None)
- `첫카페글위치`: "12.34%" 형식 또는 ''
- `블록위치`: 'head' / 'body' / ''
- `글위치`: "8.45%" 형식 또는 ''

---

## Phase 4: src/monitor.py 수정

### `monitor_keywords()` 키워드 루프 통합

#### 1. 키워드 단위 측정 (upsert_main_cafe_status 직후)

```python
# 노출된 URL 목록 수집 (삭제되지 않은 것만)
exposed_urls = [
    item['target_url'] for item in items
    if item.get('target_url') and item.get('is_deleted') != 'O'
]

# 레이아웃 측정 (키워드당 1회)
layout_result = None
try:
    layout_result = self.scraper.get_layout_metrics(keyword, exposed_urls)
    if layout_result and keyword_id:
        self.db_client.upsert_layout_info(keyword_id, layout_result)
    logging.info(f"키워드 '{keyword}' 레이아웃: has_split={layout_result.get('has_split_block')}, first_pct={layout_result.get('first_cafe_y_pct')}")
except Exception as e:
    logging.warning(f"키워드 '{keyword}' 레이아웃 측정 실패, 건너뜀: {e}")
```

**장점**:
- Selenium 호출 최소화: 키워드당 1회만 드라이버 사용
- 성능: 기존 순찰보다 추가 시간 최소 (이미 검색 결과는 존재)
- 안정성: 측정 실패가 기존 순찰 결과에 영향 없음

#### 2. 글 단위 측정 (batch_updates.append 직전)

```python
# 레이아웃 글 단위 값 추출
block_position = None
post_y_pct = None
if layout_result and target_url and exposure_status == 'O':
    url_m = layout_result.get('url_metrics', {})
    norm = self.normalize_url(target_url)
    for k, v in url_m.items():
        if self.normalize_url(k) == norm:
            block_position = v.get('block_position')
            post_y_pct = v.get('post_y_pct')
            break

batch_updates.append({
    ...기존 키들...,
    'block_position': block_position,
    'post_y_pct': post_y_pct,
})
```

**조건**:
- `layout_result` 가 정상 반환되어야 함
- `target_url` 이 존재해야 함
- `exposure_status == 'O'` (노출된 글만)

미노출 또는 삭제된 글은 자동으로 None (NULL)이 저장됩니다.

---

## 테스트 체크리스트

### 단위 테스트
- [ ] `get_layout_metrics('당뇨 초기증상', ['https://cafe.naver.com/...'], ...)` → 4개 키 모두 반환
- [ ] target_urls=[] 또는 None일 때 → url_metrics 빈 dict 반환
- [ ] 페이지 미렌더링 (scrollHeight=0) → 모두 None 반환
- [ ] 네이버 HTML 구조 변경 → has_split_block=False, first_cafe_y_pct=None 반환
- [ ] 예외 발생 (타임아웃 등) → 순찰 루프 중단 없이 다음 키워드로 진행

### 통합 테스트
- [ ] 순찰 1회 완료 후 `keyword_layout_info` 테이블에 키워드 행 존재 확인
- [ ] `keyword_patrol_logs`의 block_position, post_y_pct 컬럼 값 갱신 확인
- [ ] `get_keyword_list_from_view()` 반환 rows 길이 = 기존 17 + 4 = 21
- [ ] Google Sheets 키워드목록 시트에 신규 4개 컬럼 표시 확인

### 회귀 테스트
- [ ] 기존 is_exposed, rank, is_deleted 값이 이전과 동일하게 저장됨
- [ ] keyword_list_view의 기존 17개 컬럼 값 변동 없음

---

## 데이터 예시

### keyword_layout_info 테이블

| keyword_id | has_split_block | first_cafe_y_pct | updated_at |
|------------|-----------------|------------------|-----------|
| 1 | 1 | 15.5 | 2026-06-24 10:30:00 |
| 2 | 0 | 8.2 | 2026-06-24 10:31:00 |
| 3 | NULL | NULL | 2026-06-24 10:32:00 |

### keyword_patrol_logs 컬럼 (기존 + 신규)

| id | ... | block_position | post_y_pct | ...  |
|----|----|----------------|-----------|------|
| 1 | ... | head | 12.34 | ... |
| 2 | ... | body | 45.67 | ... |
| 3 | ... | NULL | NULL | ... |

### Google Sheets 키워드목록 시트

| ... | 비대표카페노출여부 | 상하단구분 | 첫카페글위치 | 블록위치 | 글위치 |
|-----|------------------|----------|-----------|--------|-------|
| ... | X | O | 15.5% | head | 12.3% |
| ... | O | X | 8.2% | body | 45.6% |
| ... | ? | | | | |

---

## 주의사항

### DB DDL 사전 준비

Phase 1 DDL은 **반드시 코드 실행 전에 DB에서 수동 실행**해야 합니다:

```sql
-- 1. keyword_layout_info 테이블 생성
CREATE TABLE keyword_layout_info (
    keyword_id INT NOT NULL PRIMARY KEY,
    has_split_block TINYINT(1) DEFAULT NULL,
    first_cafe_y_pct DECIMAL(5,2) DEFAULT NULL,
    updated_at DATETIME DEFAULT NULL,
    CONSTRAINT fk_layout_keyword FOREIGN KEY (keyword_id) REFERENCES keywords (keyword_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. keyword_patrol_logs 컬럼 추가
ALTER TABLE keyword_patrol_logs
    ADD COLUMN block_position ENUM('head','body') DEFAULT NULL,
    ADD COLUMN post_y_pct DECIMAL(5,2) DEFAULT NULL;

-- 3. keyword_list_view 재정의 (기존 정의 백업 후 수행)
-- SHOW CREATE VIEW keyword_list_view; 로 현재 정의 저장
DROP VIEW IF EXISTS keyword_list_view;
CREATE VIEW keyword_list_view AS
SELECT
    k.keyword                                       AS `키워드`,
    k.search_volume                                 AS `키워드조회수`,
    kr.product                                      AS `제품`,
    kr.is_deleted                                   AS `삭제`,
    kr.is_exposed                                   AS `노출`,
    kr.rank                                         AS `순위`,
    kr.is_cross_exposed                             AS `교차노출`,
    kr.cafe_name                                    AS `카페`,
    kr.published_at                                 AS `발행시간`,
    kr.result_url                                   AS `카페url`,
    kr.is_popular                                   AS `인기글여부`,
    CASE
        WHEN kmc.is_main_cafe = 0 AND kr.is_exposed = 1 THEN 'O'
        WHEN kmc.is_main_cafe IS NULL AND kr.is_exposed = 1 THEN '?'
        ELSE 'X'
    END                                             AS `비대표카페노출여부`,
    kr.cross_keyword1                               AS `교차키워드1`,
    kr.cross_keyword2                               AS `교차키워드2`,
    kr.cross_keyword3                               AS `교차키워드3`,
    kr.cross_keyword4                               AS `교차키워드4`,
    kr.cross_keyword5                               AS `교차키워드5`,
    kli.has_split_block                             AS `상하단구분`,
    kli.first_cafe_y_pct                            AS `첫카페글위치`,
    kr.block_position                               AS `블록위치`,
    kr.post_y_pct                                   AS `글위치`
FROM keyword_patrol_logs kr
JOIN keywords k ON kr.keyword_id = k.keyword_id
LEFT JOIN keyword_main_cafe kmc ON kr.keyword_id = kmc.keyword_id
LEFT JOIN keyword_layout_info kli ON kr.keyword_id = kli.keyword_id;
```

### 성능 고려사항

- Selenium 호출 추가로 순찰 소요 시간 증가 (키워드당 ~2-3초)
- 키워드 10개 기준 추가 소요 시간: ~20-30초
- 실측 필요 후 필요시 sleep 시간 조정

### 네이버 HTML 구조 변경 대응

- `_fsolid_head` / `_fsolid_body` 클래스명이 변경되면 has_split_block=NULL 반환
- 개발자도구로 실제 DOM 확인 후 JavaScript 선택자 수정 필요

---

## 파일 변경 요약

| 파일 | 변경 내용 |
|------|---------|
| `src/scraper.py` | `get_layout_metrics()` 메서드 추가 (200+ 줄) |
| `src/db_client.py` | `upsert_layout_info()` 추가, `batch_update_monitoring_results()` 확장, `get_keyword_list_from_view()` 확장 |
| `src/monitor.py` | `monitor_keywords()` 키워드 루프에 레이아웃 측정 호출 추가 (30+ 줄) |

---

## 참고: Open Question 1 해결

**문제**: 글 단위 측정을 어떻게 할 것인가?
- 옵션 A: 글마다 get_layout_metrics() 호출 (느림, 키워드당 여러 번)
- 옵션 B: 키워드당 1회 호출로 모든 URL 측정 (빠름, JavaScript 최적화)

**결정**: **옵션 B 채택**
- Selenium 호출 1회로 모든 target_urls 측정
- JavaScript에서 한 번에 모든 링크 정보 수집
- 기존 순찰 성능 영향 최소화
- 구현 완료 후 Phase 5, 6에서 검증

---

## 다음 단계 (Phase 5, 6)

### Phase 5: Google Sheets 키워드목록 시트 검증
- 시트에 R~U열(상하단구분, 첫카페글위치, 블록위치, 글위치) 표시 확인
- 각 컬럼 값 형식 검증

### Phase 6: 통합 테스트 및 성능 측정
- 키워드 3~5개로 순찰 실행 후 DB 및 시트 값 전수 확인
- 순찰 소요 시간 측정 및 허용 범위 확인
- 기존 카페 순찰 기능 회귀 테스트
