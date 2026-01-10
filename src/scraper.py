import requests
from bs4 import BeautifulSoup
import time
import random

class NaverScraper:
    def __init__(self):
        # 다양한 User-Agent 목록 정의
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 11.5; rv:90.0) Gecko/20100101 Firefox/90.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 11_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.164 Safari/537.36 Edg/91.0.864.71'
        ]
        self.base_url = "https://search.naver.com/search.naver"
        
    def get_random_user_agent(self):
        """무작위 User-Agent 반환"""
        return random.choice(self.user_agents)
        
    def get_search_results(self, keyword, page=1, delay=True):
        """네이버 검색 결과를 가져오는 함수"""
        if delay:
            # 차단 방지를 위한 랜덤 지연
            time.sleep(random.uniform(0.5, 1.5))
            
        headers = {
            "User-Agent": self.get_random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        params = {
            "query": keyword,
            "start": (page - 1) * 10 + 1
        }
        
        try:
            print(f"'{keyword}' 검색 중 (페이지 {page})...")
            response = requests.get(self.base_url, params=params, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup
        except Exception as e:
            print(f"검색 결과 가져오기 실패: {str(e)}")
            return None
            
    def extract_urls(self, soup):
        """검색 결과에서 URL을 추출하는 함수"""
        urls = []
        
        # 1. 가장 효과적인 방법: 모든 a 태그를 검색하고 모든 속성 확인
        print("모든 a 태그에서 URL 추출 시도...")
        try:
            for a_tag in soup.find_all('a'):
                # 모든 속성 확인
                for attr_name, attr_value in a_tag.attrs.items():
                    # URL 형태인 모든 속성 값 추출
                    if isinstance(attr_value, str) and ('http://' in attr_value or 'https://' in attr_value):
                        # 네이버 URL에 초점
                        if 'naver.com' in attr_value:
                            urls.append(attr_value)
                            #print(f"네이버 URL 발견 (속성: {attr_name}): {attr_value[:100]}..." if len(attr_value) > 100 else f"네이버 URL 발견: {attr_value}")
        except Exception as e:
            print(f"a 태그 처리 중 오류: {str(e)}")
        
        # 2. 구조적 접근: 네이버 검색 결과에서 자주 사용되는 패턴 찾기
        try:
            # nocr 속성이 있는 요소 찾기 (네이버 검색 결과에 자주 사용됨)
            nocr_elements = soup.find_all(attrs={'nocr': True})
            print(f"{len(nocr_elements)}개의 nocr 속성 요소 발견")
            
            for elem in nocr_elements:
                # 링크 요소이거나 내부에 링크를 포함하는지 확인
                if elem.name == 'a' and elem.has_attr('href'):
                    urls.append(elem['href'])
                else:
                    # 내부 링크 찾기
                    for inner_a in elem.find_all('a', href=True):
                        urls.append(inner_a['href'])
        except Exception as e:
            print(f"nocr 요소 처리 중 오류: {str(e)}")
        
        # 3. 일반적인 컨테이너 클래스 접근
        # 클래스 이름은 동적으로 변경되지만, 일부 공통 패턴이 있음
        try:
            # 일반적인 검색 결과 컨테이너
            containers = []
            
            # 클래스 수가 많은 div 탐색 (네이버 검색은 일반적으로 많은 클래스를 사용)
            for div in soup.find_all('div'):
                if div.has_attr('class') and len(div['class']) >= 2:
                    containers.append(div)
            
            print(f"{len(containers)}개의 잠재적 컨테이너 발견")
            
            # 각 컨테이너 내의 링크 찾기
            for container in containers:
                for a in container.find_all('a', href=True):
                    if 'naver.com' in a['href']:
                        urls.append(a['href'])
        except Exception as e:
            print(f"컨테이너 처리 중 오류: {str(e)}")
        
        # 4. 텍스트 기반 접근
        # 특정 키워드와 함께 출현할 가능성이 높은 링크 찾기
        keywords = ["cafe", "blog", "카페", "블로그", "지식인", "포스트", "뉴스"]
        
        try:
            for keyword in keywords:
                # 텍스트에 키워드가 포함된 요소 근처의 링크 찾기
                for element in soup.find_all(text=lambda t: keyword in t.lower() if t else False):
                    parent = element.parent
                    # 부모 요소와 그 형제 요소에서 링크 찾기
                    for a in parent.find_all('a', href=True):
                        if 'naver.com' in a['href']:
                            urls.append(a['href'])
                    # 상위 요소도 확인
                    if parent.parent:
                        for a in parent.parent.find_all('a', href=True):
                            if 'naver.com' in a['href']:
                                urls.append(a['href'])
        except Exception as e:
            print(f"키워드 기반 검색 중 오류: {str(e)}")
        
        # 네이버 카페/블로그 URL 정규화 (JWT 토큰 제거)
        normalized_urls = []
        for url in urls:
            # 기본 패턴 추출
            if 'cafe.naver.com' in url or 'blog.naver.com' in url:
                # 기본 URL 추출 (복잡한 쿼리 파라미터 제거)
                base_url = url.split('?')[0]
                # 특정 패턴 제거 (ZXh0ZXJu... 같은 인코딩된 부분)
                if '=' in base_url:
                    base_url = base_url.split('=')[0]
                normalized_urls.append(base_url)
            else:
                normalized_urls.append(url)
        
        # 중복 URL 제거
        unique_urls = list(dict.fromkeys(normalized_urls))
        print(f"총 {len(unique_urls)}개의 고유 URL을 추출했습니다.")
        
        # 디버깅: 모든 URL 출력
        if unique_urls:
            print("추출된 URL 목록:")
        
        return unique_urls