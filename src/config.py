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

# 카페 랭킹 분석 시트 설정
CAFE_RANKING_SHEETS_ID = os.getenv('CAFE_RANKING_SHEETS_ID', '')
CAFE_RANKING_SHEETS_GID = int(os.getenv('CAFE_RANKING_SHEETS_GID', 0))

# 카페 URL slug → 단축 이름 매핑
CAFE_URL_MAP = {
    # 지역/일상
    'pusanmommy': '부산맘',
    'culturebloom': '컬처블룸',
    'fox5282': 'a+여우야',
    'zoozoocom': '키작아',
    'gimhaezumma': '줌마렐라(김해)',
    'masanmam': '줌마렐라(마산)',
    'shopjirmsin': '쇼핑의지름신',
    'magic26': '미엘맘스비',
    # 건강
    'peopledisc': '척추',
    'rksghwhantk': '전간조',
    'move79': '해돌',
    'tripworldwater': '불면증',
    'lung': '폐암환우',
    'amwinner': '암승모',
    'pcainfo': '전립선암',
    # 상담/부동산
    'qnamaster': '고민상담관',
    'rainup': '아름다운내집갖기',
    'mindy7857': '베나자',
    'ckgusqlswkd': '위편사',
    'kookminlease': '국민공공민간임대아파트들어가기',
    'gangmok': '강남엄마VS목동엄마',
    'dj114': '당진 부동산',
    'jaegebal': '부동산 스터디',
    'ehdxks2': '동탄2신도시 분양',
    # 게임
    'minecraftpe': '푸꾸옥',
    'crkingdom': '쿠키런',
    'appleiphone': '아사모',
    'inmacbook': '맥사람들',
    'wtac': '동물의숲',
    'lolkor': 'LOL',
    'anycallusershow': '갤폴드7',
    'onimobile': '좀비고등학교',
    'pikmins': '피크민',
    'identity5': '제5인격',
    'pes2017mobile': '이풋볼 2026',
    'honkaistarrail': '붕괴',
    'xst': '샤오미스토리',
    'playbattlegrounds': '배그공식카페',
    'mafia42': '마피아42',
    # 재테크/경제
    'dokkm': '독금사',
    'stocktraining': '나는주식트레이더다',
    'cafe1535': '복지아는게힘',
    'studycool': '영유나라',
    'divclub': '배당투자자모임',
    'soho': '셀러오션',
    'aclove': '경리회계쉼터',
    'engmstudy': '짠돌이카페',
    'gangseogu': '예산회계실무',
    'mkas1': '행복재테크',
    'postmore': '꿀 통',
    'qormsrnr': '뺑구닷컴',
    'wjdrkrjqn': '정가거부',
    'ccrs5500': '신용회복위원회 공식카페',
    'ustock': '평생주식카페',
    'geobuk2': '거북이투자법',
    'anycard': '신용카드 박물관',
    'onepieceholicplus': '월급쟁이 재테크 연구카페',
    '1djr58': '가투법',
    # 교육/공부
    'goldschools': '특목고갈사람모여',
    'studentstudyhard': '공준모',
    'nursingstudies': '간준모',
    'mathall': '상위1%카페',
    'nexontv': '비트맨',
    'pnmath': '포만한 수학 연구소',
    'romul': '로물콘',
    'dokchi': '독취사',
    'yoondyedu': '윤도영통합과학시스템',
    'makegoodstudy': '성공하는 공부방 운영하기',
    'mbticafe': 'MBTI 심리 카페',
    'michiexam': '기출비',
    'ebook': '디지털감성 e북카페',
    'suhui': '수만휘',
    'drivingbus': '버스를 운전하는 사람들',
    'chokingwang': '교준모',
    'mom79': '초등맘',
    'power119': '전기박사',
    'm2school': '독공사',
    'getampethskin': '거북맘vs토끼맘',
    'dakchi': '공취모',
    'jmeat': '고창모',
    # 취미/생활
    'jihosoccer123': '아프니까사장이다',
    'ayshh': '아영이네',
    'de4rum': '디테일링포럼',
    'clubpet': '냥이네',
    'healingdogcat': '아반강고',
    'winerack24': '와쌉',
    'fujipeople': '후지피플',
    'dodohi0607': '화폐 수집 1090',
    'zootopiamembership': '에버랜드 동물원 주토피아',
    'dogpalza': '강사모',
    'familygarden': '텃밭과 채소키우기',
    'nex3nex5': '소니 미러리스 클럽',
    'watchholic': '와치홀릭',
    'bricknara': '브릭나라[BrickNara] 레고 Lego',
    'hby': '열대어no.1 작은개울 홈다리',
    'perfectshine': 'perfectshine',
    'baekparrotlove': '앵사모',
    'gcd': '모두의 건프라',
    'loyaltylife': '뉴스사사',
    'movie02': '네영카',
    # 여행
    'hawaiiphoto': '포에버 하와이',
    'loveloveloveovelove': '보홀트래블',
    'jejutip': '느영나영',
    'momsolleh': '체크인유럽',
    'worldtravelcafe': '오사카홀릭',
    'hotellife': '스사사',
    'taesarang': '태사랑',
    'jpnstory': '네일동',
    'jalanjalanindonesia': '잘란 잘란 인도네시아',
    'cebu100x': '세부100배즐기기',
    'tgpia': '살통영',
    'firenze': '유랑',
    'nyctourdesign': '미여디',
    'vinpearl': '베트남 피크타임',
    'waateam': 'Flighters 항공우주 커뮤니티',
    'mumumhoju': '머뭄 호주여행 & 뉴질랜드 여행',
    'guamfree': '괌 자유여행 길잡이',
    'okinawago': '오키나와 달인 카페',
    'foreverhk': '포에버 홍콩',
    'taiwantour': '즐거운 대만여행',
    'joycamping': '달구지 캠핑',
    'thaiinfo': '태초의 태국정보',
    'jinsimdietcafe': '진심다이어트',
    'gray0kpov': '백세건강클럽',
    'bluegeeri': '여사친',
    'dangzero': '당뇨 약없이 관리하기',
    'mountainstory': '아름다운등산일기',
    'gungangfoodstory': '건강한식단일기',
    'smartmommy1': '똑순이엄마',
    'gungangcafe1': '건강백신',
    'kidzcafelist': '키즈카페',
    'workee': '직장인 탐구생활',
    'livehope': '아름다운동행',
    'happyeverycvs': '행복한편의점',
    'skybluezw4rh' :'맘이베베',
    'cantsb' :'씨씨앙',
    'wjswnaka' :'전주전북맘',
    'yangmom' :'양평맘',
    'uvacenter':'유방암이야기',
    'dongtanmom':'동탄맘',
    'moms1004':'검암맘',
    'dgmom365':'대구맘',
    'thyroidcancers' :'갑상선포럼',
    'kig':'피터팬의 좋은방 구하기',
}

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