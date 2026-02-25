"""
시스템 설정 변수 관리 모듈
"""

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
GOOGLE_SHEETS_ID = '1aaFJtLXDaIK_iKd4Y8ZEnNxw2xoS9rfkZKggQ0ncbdw'
# GOOGLE_SHEETS_ID = '1wssRTS1SS4AZrjlSR_joU8I7zFWeKwMvS6Cdaoxnnm4'  #테스트용

# 시트 GID (URL의 gid= 파라미터)
GOOGLE_SHEETS_GID = 1011348622

# 서비스 계정 인증 JSON 파일 경로
GOOGLE_CREDENTIALS_PATH = 'config/credentials.json'

# ===========================================
# 이메일 설정
# ===========================================

EMAIL_SENDER = "fmonecompany@gmail.com"  # 발신자 이메일
EMAIL_PASSWORD = "ugbq mgvv wtat sdbn"  # Gmail의 경우 앱 비밀번호 필요
EMAIL_RECIPIENTS = ["lkm1416@gmail.com", "nnf2913@gmail.com"]  # 수신자 이메일 목록
# EMAIL_RECIPIENTS = ["lkm1416@gmail.com"]  # 수신자 이메일 목록

# 카테고리별 한글 이름 매핑
CATEGORY_NAMES = {
    'cancer': '암 카테고리',
    'diabetes': '당뇨 카테고리',
    'cream': '갱년기 카테고리'
}