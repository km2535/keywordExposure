"""
검색 결과 시각화 스크립트

1. 필요한 라이브러리 설치
2. JSON 파일에서 데이터 불러오기
3. 데이터 전처리
4. 시각화 그래프 생성
"""

# 1. 필요한 라이브러리 설치
import subprocess
import sys

def install_packages():
    """필요한 패키지 설치"""
    required_packages = ['matplotlib', 'seaborn', 'pandas']
    
    for package in required_packages:
        try:
            # 패키지 import 시도
            __import__(package)
            print(f"{package} 이미 설치되어 있습니다.")
        except ImportError:
            # 패키지가 설치되어 있지 않으면 설치
            print(f"{package} 설치 중...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"{package} 설치 완료!")

# 패키지 설치 실행
print("필요한 패키지 설치 확인 중...")
install_packages()

# 2. 라이브러리 임포트
import json
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import re
from datetime import datetime

# 3. JSON 파일에서 데이터 불러오기
def load_data(file_path):
    """JSON 파일에서 데이터 불러오기"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        print(f"데이터를 성공적으로 불러왔습니다: {file_path}")
        return data
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {file_path}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"JSON 파일 형식이 잘못되었습니다: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"데이터 로딩 중 오류 발생: {str(e)}")
        sys.exit(1)

# 데이터 불러오기
data = load_data('data/latest_results.json')

# 4. 카페 이름 추출 함수
def extract_cafe_name(url):
    """URL에서 카페 이름 추출"""
    try:
        match = re.search(r'cafe\.naver\.com\/([^\/]+)', url)
        if match:
            return match.group(1)
        return '알 수 없음'
    except:
        return '알 수 없음'

# 5. 데이터 전처리
def preprocess_data(data):
    """검색 결과 데이터 전처리"""
    rows = []
    for result in data['results']:
        keyword = result['keyword']
        for url_data in result['urls']:
            cafe_name = extract_cafe_name(url_data['url'])
            exposure_status = '노출' if url_data['is_exposed'] else '비노출'
            rows.append({
                'keyword': keyword,
                'cafe': cafe_name,
                'url': url_data['url'],
                'status': exposure_status,
                'is_exposed': 1 if url_data['is_exposed'] else 0
            })
    
    return pd.DataFrame(rows)

# 데이터프레임 생성
df = preprocess_data(data)
print("데이터 전처리 완료")
print(f"총 {len(df)} 개의 URL 정보가 있습니다.")

# 6. 시각화 함수
def visualize_search_results(df, data_timestamp):
    """검색 결과 시각화"""
    plt.figure(figsize=(12, 10))
    
    # 한글 폰트 설정 시도
    try:
        plt.rcParams['font.family'] = 'Malgun Gothic'  # 윈도우 한글 폰트
        plt.rcParams['axes.unicode_minus'] = False
    except:
        try:
            plt.rcParams['font.family'] = 'AppleGothic'  # macOS 한글 폰트
            plt.rcParams['axes.unicode_minus'] = False
        except:
            print("한글 폰트 설정에 실패했습니다. 기본 폰트를 사용합니다.")
    
    # 색상 설정
    colors = {'노출': '#2ecc71', '비노출': '#e74c3c'}
    
    # 1. 키워드별 노출/비노출 상태 시각화
    plt.subplot(2, 1, 1)
    sns.countplot(
        data=df, 
        x='keyword', 
        hue='status',
        palette=colors,
        hue_order=['노출', '비노출']
    )
    plt.title('키워드별 노출 상태', fontsize=14, pad=20)
    plt.xlabel('검색 키워드', fontsize=12)
    plt.ylabel('URL 수', fontsize=12)
    plt.legend(title='노출 상태')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 2. 카페별 노출 상태 시각화
    plt.subplot(2, 1, 2)
    
    # 카페별 평균 노출 상태 계산
    cafe_exposure = df.groupby(['cafe', 'keyword'])['is_exposed'].mean().reset_index()
    
    sns.barplot(
        data=cafe_exposure,
        x='cafe',
        y='is_exposed',
        hue='keyword',
        errorbar=None
    )
    plt.title('카페별 노출 상태', fontsize=14, pad=20)
    plt.xlabel('카페 이름', fontsize=12)
    plt.ylabel('노출 비율 (0~1)', fontsize=12)
    plt.yticks([0, 0.5, 1], ['비노출', '일부 노출', '모두 노출'])
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # 타임스탬프 표시
    try:
        timestamp_dt = datetime.strptime(data_timestamp, '%Y-%m-%d %H:%M:%S')
        formatted_time = timestamp_dt.strftime('%Y년 %m월 %d일 %H:%M:%S')
    except:
        formatted_time = data_timestamp
    
    plt.figtext(0.5, 0.01, f'검색 시간: {formatted_time}', ha='center', fontsize=10, style='italic')
    
    # 레이아웃 조정
    plt.tight_layout(pad=3.0)
    
    # 그래프 저장
    output_file = 'search_results_visualization.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"시각화 이미지가 저장되었습니다: {output_file}")
    
    # 그래프 표시
    plt.show()

# 7. 시각화 실행
print("시각화 그래프 생성 중...")
visualize_search_results(df, data['timestamp'])
print("시각화 완료!")