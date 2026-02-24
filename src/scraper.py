import requests
from bs4 import BeautifulSoup
import time
import random
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import UnexpectedAlertPresentException, NoAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager
import logging

class NaverScraper:
    def __init__(self):
        # Selenium WebDriver (삭제 확인용, 필요시 초기화)
        self._driver = None

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

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        URL 정규화 (단일 공통 로직):
          1. 쿼리 파라미터(?...) 제거
          2. 카페/블로그 URL의 JWT 토큰(=token) 제거
          3. 모바일 도메인(m.) 제거
        """
        if not url:
            return ''
        base_url = url.split('?')[0]
        if ('cafe.naver.com' in base_url or 'blog.naver.com' in base_url) and '=' in base_url:
            base_url = base_url.split('=')[0]
        parsed = urlparse(base_url)
        normalized_netloc = parsed.netloc.replace('m.', '', 1)
        return normalized_netloc + parsed.path

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
            logging.info(f"'{keyword}' 검색 중 (페이지 {page})...")
            response = requests.get(self.base_url, params=params, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup
        except Exception as e:
            logging.info(f"검색 결과 가져오기 실패: {str(e)}")
            return None
            
    def extract_urls(self, soup):
        """검색 결과에서 URL을 추출하는 함수"""
        urls = []
        
        # 1. 가장 효과적인 방법: 모든 a 태그를 검색하고 모든 속성 확인
        logging.info("모든 a 태그에서 URL 추출 시도...")
        try:
            for a_tag in soup.find_all('a'):
                # 모든 속성 확인
                for attr_name, attr_value in a_tag.attrs.items():
                    # URL 형태인 모든 속성 값 추출
                    if isinstance(attr_value, str) and ('http://' in attr_value or 'https://' in attr_value):
                        # 네이버 URL에 초점
                        if 'naver.com' in attr_value:
                            urls.append(attr_value)
                            #logging.info(f"네이버 URL 발견 (속성: {attr_name}): {attr_value[:100]}..." if len(attr_value) > 100 else f"네이버 URL 발견: {attr_value}")
        except Exception as e:
            logging.info(f"a 태그 처리 중 오류: {str(e)}")
        
        # 2. 구조적 접근: 네이버 검색 결과에서 자주 사용되는 패턴 찾기
        try:
            # nocr 속성이 있는 요소 찾기 (네이버 검색 결과에 자주 사용됨)
            nocr_elements = soup.find_all(attrs={'nocr': True})
            logging.info(f"{len(nocr_elements)}개의 nocr 속성 요소 발견")
            
            for elem in nocr_elements:
                # 링크 요소이거나 내부에 링크를 포함하는지 확인
                if elem.name == 'a' and elem.has_attr('href'):
                    urls.append(elem['href'])
                else:
                    # 내부 링크 찾기
                    for inner_a in elem.find_all('a', href=True):
                        urls.append(inner_a['href'])
        except Exception as e:
            logging.info(f"nocr 요소 처리 중 오류: {str(e)}")
        
        # 3. 일반적인 컨테이너 클래스 접근
        # 클래스 이름은 동적으로 변경되지만, 일부 공통 패턴이 있음
        try:
            # 일반적인 검색 결과 컨테이너
            containers = []
            
            # 클래스 수가 많은 div 탐색 (네이버 검색은 일반적으로 많은 클래스를 사용)
            for div in soup.find_all('div'):
                if div.has_attr('class') and len(div['class']) >= 2:
                    containers.append(div)
            
            logging.info(f"{len(containers)}개의 잠재적 컨테이너 발견")
            
            # 각 컨테이너 내의 링크 찾기
            for container in containers:
                for a in container.find_all('a', href=True):
                    if 'naver.com' in a['href']:
                        urls.append(a['href'])
        except Exception as e:
            logging.info(f"컨테이너 처리 중 오류: {str(e)}")
        
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
            logging.info(f"키워드 기반 검색 중 오류: {str(e)}")
        
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
        logging.info(f"총 {len(unique_urls)}개의 고유 URL을 추출했습니다.")
        
        # 디버깅: 모든 URL 출력
        if unique_urls:
            logging.info("추출된 URL 목록:")

        return unique_urls

    def extract_main_urls(self, soup):
        """
        메인 노출 URL만 추출.
        data-heatmap-target=".link" 인 a 태그만 메인 노출로 판단.
        data-heatmap-target=".series" 는 서브 노출이므로 제외.
        """
        urls = []
        try:
            for a_tag in soup.find_all('a', attrs={'data-heatmap-target': '.link'}):
                href = a_tag.get('href', '')
                if href and ('http://' in href or 'https://' in href):
                    urls.append(href)
        except Exception as e:
            logging.info(f"메인 URL 추출 중 오류: {str(e)}")

        normalized_urls = [self.normalize_url(url) for url in urls]
        unique_urls = list(dict.fromkeys(normalized_urls))
        logging.info(f"메인 노출(data-heatmap-target='.link') URL {len(unique_urls)}개 추출 완료")
        return unique_urls

    def get_cafe_post_views(self, url):
        """
        네이버 카페 글의 조회수를 가져오는 함수

        Args:
            url: 카페 글 URL (예: https://cafe.naver.com/fox5282/4668750)

        Returns:
            조회수 (int) 또는 None (실패 시)
        """
        if not url or 'cafe.naver.com' not in url:
            return None

        try:
            # 랜덤 지연
            time.sleep(random.uniform(0.3, 0.8))

            headers = {
                "User-Agent": self.get_random_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
            }

            response = requests.get(url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 방법 1: 조회수 텍스트 찾기 (일반적인 패턴)
            # "조회 123" 또는 "조회수 123" 형태
            view_patterns = [
                soup.find('span', class_='count'),  # 일반적인 클래스
                soup.find('span', string=lambda t: t and '조회' in t),
                soup.find('em', class_='u_cnt'),
            ]

            for element in view_patterns:
                if element:
                    text = element.get_text(strip=True)
                    # 숫자만 추출
                    import re
                    numbers = re.findall(r'[\d,]+', text)
                    if numbers:
                        views = int(numbers[0].replace(',', ''))
                        return views

            # 방법 2: 특정 구조 찾기
            # 네이버 카페 조회수는 보통 특정 div 안에 있음
            article_info = soup.find('div', class_='article_info')
            if article_info:
                view_elem = article_info.find('span', class_='count')
                if view_elem:
                    text = view_elem.get_text(strip=True)
                    import re
                    numbers = re.findall(r'[\d,]+', text)
                    if numbers:
                        return int(numbers[0].replace(',', ''))

            # 방법 3: 전체 텍스트에서 "조회" 패턴 찾기
            page_text = soup.get_text()
            import re
            view_match = re.search(r'조회[수]?\s*[:\s]*(\d[\d,]*)', page_text)
            if view_match:
                return int(view_match.group(1).replace(',', ''))

            return None

        except Exception as e:
            logging.info(f"조회수 가져오기 실패 ({url}): {str(e)}")
            return None

    def _init_driver(self):
        """Selenium WebDriver 초기화 (삭제 확인용)"""
        if self._driver is None:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--log-level=3')  # 로그 최소화
            chrome_options.add_argument('--incognito')  # 시크릿 모드
            chrome_options.add_argument('--disable-application-cache')  # 앱 캐시 비활성화
            chrome_options.add_argument('--disable-cache')  # 디스크 캐시 비활성화
            chrome_options.add_argument(f'user-agent={self.get_random_user_agent()}')

            self._driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            logging.info("Selenium WebDriver 초기화 완료")

        return self._driver

    def clear_cache_and_cookies(self):
        """WebDriver의 캐시와 쿠키를 모두 초기화"""
        if self._driver:
            try:
                self._driver.delete_all_cookies()
                # Chrome DevTools Protocol로 브라우저 캐시 완전 삭제
                self._driver.execute_cdp_cmd('Network.clearBrowserCache', {})
                self._driver.execute_cdp_cmd('Network.clearBrowserCookies', {})
                print("브라우저 캐시 및 쿠키 초기화 완료")
            except Exception as e:
                print(f"캐시/쿠키 초기화 중 오류 (무시): {str(e)}")

    def reset_driver(self):
        """WebDriver를 완전히 종료하고 새로 시작 (캐시/쿠키 완전 초기화)"""
        self.close_driver()
        print("WebDriver 리셋 완료 - 다음 사용 시 새로 초기화됩니다.")

    def close_driver(self):
        """WebDriver 종료"""
        if self._driver:
            self._driver.quit()
            self._driver = None
            logging.info("Selenium WebDriver 종료")

    def check_post_deleted(self, url):
        """
        네이버 카페 게시글 삭제 여부 확인

        Args:
            url: 카페 글 URL (예: https://cafe.naver.com/fox5282/4668750)

        Returns:
            tuple: (is_deleted: bool, message: str or None)
                - is_deleted: True면 삭제됨, False면 존재함, None이면 확인 실패
                - message: 삭제 메시지 또는 에러 메시지
        """
        if not url or 'cafe.naver.com' not in url:
            return None, "유효하지 않은 URL"

        try:
            driver = self._init_driver()

            driver.get(url)
            time.sleep(1.5)  # alert 대기

            try:
                # JavaScript alert 확인
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()  # alert 닫기

                if '삭제' in alert_text or '존재하지 않' in alert_text:
                    return True, alert_text
                return False, None

            except NoAlertPresentException:
                # alert이 없으면 글이 존재함
                return False, None

        except UnexpectedAlertPresentException as e:
            # alert이 있으면 삭제된 글
            return True, "삭제되었거나 존재하지 않는 게시글"
        except Exception as e:
            logging.info(f"삭제 확인 실패 ({url}): {str(e)}")
            return None, str(e)

    def batch_check_posts_deleted(self, urls):
        """
        여러 게시글의 삭제 여부를 일괄 확인

        Args:
            urls: URL 목록 [(url, row_id), ...]

        Returns:
            list: [{'url': url, 'row': row_id, 'is_deleted': bool, 'message': str}, ...]
        """
        results = []

        try:
            for url, row_id in urls:
                is_deleted, message = self.check_post_deleted(url)
                results.append({
                    'url': url,
                    'row': row_id,
                    'is_deleted': is_deleted,
                    'message': message
                })

                # API 레이트 리밋 방지
                time.sleep(random.uniform(0.5, 1.0))

        finally:
            # 작업 완료 후 드라이버 종료
            self.close_driver()

        return results