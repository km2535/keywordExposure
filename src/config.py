"""
시스템 설정 변수 관리 모듈
"""

import os
from dotenv import load_dotenv

load_dotenv()

# 출력 디렉토리 경로
OUTPUT_DIR = '/var/www/keywordE/build/data'
# OUTPUT_DIR = 'data'

# 설정 파일 기본 경로
CONFIG_DIR = 'config'

# 데이터 파일 기본 경로
DATA_DIR = 'data'
# 지원하는 카테고리 목록
CATEGORIES = ['cancer', 'diabetes', 'cream']

# 검색할 기본 페이지 수
DEFAULT_PAGES = 1

# 스케줄러 실행 간격 (시간)
# SCHEDULER_INTERVAL = 6

# ===========================================
# Google Sheets 설정
# ===========================================

# Google Sheets 문서 ID
GOOGLE_SHEETS_ID = '1v_NIETEm_NMTx2nnn1de77uDKVzfCGE0CLEfy5dxvBU'
# GOOGLE_SHEETS_ID = '1wssRTS1SS4AZrjlSR_joU8I7zFWeKwMvS6Cdaoxnnm4'  #테스트용

# 시트 GID (URL의 gid= 파라미터)
GOOGLE_SHEETS_GID = 1011348622

# 서비스 계정 인증 JSON 파일 경로
GOOGLE_CREDENTIALS_PATH = 'config/credentials.json'

# 키워드목록 시트 설정
KEYWORD_LIST_SHEETS_ID = '1XGzfO6SL6-WtlBVG5hEg_WFBUC_dgkqdknf5_-fgFZQ'
KEYWORD_LIST_SHEETS_GID = 1499466916

# 블로그순찰 시트 설정
BLOG_SHEETS_ID = os.getenv('BLOG_SHEETS_ID', '')
BLOG_SHEETS_GID = int(os.getenv('BLOG_SHEETS_GID', 0))

# 블로그 키워드목록 시트 설정
BLOG_KEYWORD_LIST_SHEETS_ID = os.getenv('BLOG_KEYWORD_LIST_SHEETS_ID', '')
BLOG_KEYWORD_LIST_SHEETS_GID = int(os.getenv('BLOG_KEYWORD_LIST_SHEETS_GID', 0))

# ===========================================
# DB 설정
# ===========================================

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 3306))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'cafe_auto')
DB_TABLE = os.getenv('DB_TABLE', 'keyword_patrol_logs')

# 카테고리별 한글 이름 매핑
CATEGORY_NAMES = {
    'cancer': '암 카테고리',
    'diabetes': '당뇨 카테고리',
    'cream': '갱년기 카테고리'
}