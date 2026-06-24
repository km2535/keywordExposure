import copy
import requests
from bs4 import BeautifulSoup
import time
import random
from urllib.parse import urlparse
from typing import Optional
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

        # 다양한 User-Agent 목록 정의 (최신 버전)
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        ]
        self._session = requests.Session()
        self.base_url = "https://search.naver.com/search.naver"
        
    def get_random_user_agent(self):
        """무작위 User-Agent 반환"""
        return random.choice(self.user_agents)

    def resolve_short_url(self, url: str) -> str:
        """
        단축 URL(naver.me 등)을 실제 URL로 추적.
        리다이렉트 체인을 따라가 최종 URL 반환.
        실패 시 원본 URL 반환.
        """
        if not url or 'naver.me' not in url:
            return url
        try:
            resp = self._session.head(
                url, allow_redirects=True, timeout=10,
                headers={"User-Agent": self.get_random_user_agent()}
            )
            return resp.url
        except Exception:
            try:
                resp = self._session.get(
                    url, allow_redirects=True, timeout=10,
                    headers={"User-Agent": self.get_random_user_agent()}
                )
                return resp.url
            except Exception:
                return url

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        URL 정규화 (단일 공통 로직):
          1. 쿼리 파라미터(?...) 제거
          2. 카페/블로그 URL의 JWT 토큰(=token) 제거
          3. 모바일 도메인(m.) 제거 — netloc이 'M.' 으로 시작하는 경우만
        """
        if not url:
            return ''
        base_url = url.split('?')[0]
        if ('cafe.naver.com' in base_url or 'blog.naver.com' in base_url) and '=' in base_url:
            base_url = base_url.split('=')[0]
        parsed = urlparse(base_url)
        netloc = parsed.netloc
        if netloc.startswith('m.'):
            netloc = netloc[2:]
        return netloc + parsed.path

    def get_search_results(self, keyword, page=1, delay=True):
        """네이버 검색 결과를 가져오는 함수 (requests 우선, 403 시 Selenium 폴백)"""
        if delay:
            time.sleep(random.uniform(0.5, 1.0))

        from urllib.parse import urlencode
        params = urlencode({"query": keyword, "start": (page - 1) * 10 + 1})
        url = f"{self.base_url}?{params}"

        logging.info(f"'{keyword}' 검색 중 (페이지 {page})...")

        # 1단계: requests 시도 (빠름)
        # 매 검색마다 새 세션 사용 → 쿠키/세션 누적 없이 "처음 방문자" 상태로 검색
        try:
            fresh_session = requests.Session()
            headers = {
                "User-Agent": self.get_random_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "identity",
                "Referer": "https://www.naver.com/",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            response = fresh_session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            # 실제 검색 결과가 있는지 확인 (봇 차단 페이지는 결과 없음)
            # data-heatmap-target 속성 또는 네이버 검색 결과 컨테이너(sds-comps) 중 하나라도 있으면 유효
            has_results = (
                soup.find('a', attrs={'data-heatmap-target': True}) is not None
                or soup.find(class_=lambda c: c and 'sds-comps' in ' '.join(c) if isinstance(c, list) else c and 'sds-comps' in c) is not None
            )
            if has_results:
                return soup
            logging.info(f"requests 결과 없음 (봇 차단 추정), Selenium으로 전환")
        except Exception as e:
            logging.info(f"requests 실패 ({e}), Selenium으로 전환")

        # 2단계: Selenium 폴백 (느리지만 확실)
        # 쿠키 초기화 후 검색 — 처음 방문자 상태 유지
        for attempt in range(2):
            try:
                driver = self._init_driver()
                driver.delete_all_cookies()
                driver.get(url)
                time.sleep(random.uniform(1.5, 2.0))
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                return soup
            except Exception as e:
                logging.info(f"Selenium 실패 (시도 {attempt+1}): {str(e)}")
                self.close_driver()
                if attempt == 0:
                    time.sleep(2)
        return None
            
    def extract_urls(self, soup):
        """검색 결과에서 URL을 추출하는 함수"""
        urls = []
        
        # 1. 가장 효과적인 방법: 모든 a 태그를 검색하고 모든 속성 확인
        logging.info("모든 a 태그에서 URL 추출 시도...")
        try:
            for a_tag in soup.find_all('a'):
                # 모든 속성 확인
                for _, attr_value in a_tag.attrs.items():
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
        1순위: data-heatmap-target=".link" 인 a 태그
        2순위(폴백): data-heatmap-target 속성이 있는 모든 a 태그 중 naver.com 포함 URL
        data-heatmap-target=".series" 는 서브 노출이므로 제외.
        fds-health-cafe-block-wrap(관련 경험 카페글) 섹션은 제외.
        """
        # 관련 경험 카페글 섹션을 soup에서 제거한 뒤 탐색
        search_soup = copy.copy(soup)
        for health_block in search_soup.find_all('div', class_=lambda c: c and 'fds-health-cafe-block-wrap' in c):
            health_block.decompose()

        urls = []
        try:
            for a_tag in search_soup.find_all('a', attrs={'data-heatmap-target': lambda v: v in ('.link', '.imgtitlelink')}):
                href = a_tag.get('href', '')
                if href and ('http://' in href or 'https://' in href):
                    urls.append(href)
        except Exception as e:
            logging.info(f"메인 URL 추출 중 오류: {str(e)}")

        # 폴백: .link 속성 방식으로 URL을 하나도 못 찾은 경우 — 네이버 HTML 구조 변경 감지
        if not urls:
            logging.warning("data-heatmap-target='.link' URL 없음 — 네이버 HTML 구조 변경 의심, 폴백 추출 시도")
            try:
                for a_tag in search_soup.find_all('a', attrs={'data-heatmap-target': True}):
                    target_val = a_tag.get('data-heatmap-target', '')
                    if '.series' in target_val:
                        continue
                    href = a_tag.get('href', '')
                    if href and 'naver.com' in href and ('http://' in href or 'https://' in href):
                        urls.append(href)
            except Exception as e:
                logging.warning(f"폴백 URL 추출 중 오류: {str(e)}")

        normalized_urls = [self.normalize_url(url) for url in urls]
        unique_urls = list(dict.fromkeys(normalized_urls))
        if not unique_urls:
            logging.warning("extract_main_urls: 추출된 URL 0개 — 봇 차단 또는 HTML 구조 변경 가능성")
        else:
            logging.info(f"메인 노출 URL {len(unique_urls)}개 추출 완료")
        return unique_urls

    def extract_popular_post_urls(self, soup):
        """
        검색 결과에서 인기글 섹션에 속한 URL 집합 반환.
        h2 텍스트에 '인기글'이 포함된 sds-comps-header-title 섹션을 찾아
        해당 섹션 내 data-heatmap-target=".link" URL을 추출.
        인기글 섹션이 없으면 빈 집합 반환.
        """
        popular_urls = set()
        try:
            all_header_titles = soup.find_all('div', class_=lambda c: c and 'sds-comps-header-title' in c)
            logging.info(f"[인기글] sds-comps-header-title 개수: {len(all_header_titles)}")
            for i, header_title in enumerate(all_header_titles):
                h2 = header_title.find('h2')
                h2_text = h2.get_text(strip=True) if h2 else None
                logging.info(f"[인기글] header_title[{i}] h2={h2_text!r}")
                if not h2 or '인기글' not in h2.get_text():
                    continue
                section = header_title.parent.parent  # sds-comps-header의 부모 (header + 글목록 모두 포함)
                if section is None:
                    logging.info(f"[인기글] section is None, 스킵")
                    continue
                links = section.find_all('a', attrs={'data-heatmap-target': '.link'})
                logging.info(f"[인기글] section 내 .link 개수: {len(links)}")
                for a_tag in links:
                    href = a_tag.get('href', '')
                    if href and ('http://' in href or 'https://' in href):
                        popular_urls.add(self.normalize_url(href))
        except Exception as e:
            logging.info(f"인기글 URL 추출 중 오류: {str(e)}")
        logging.info(f"인기글 섹션 URL {len(popular_urls)}개 추출 완료")
        return popular_urls

    def check_all_main_cafe(self, soup) -> bool:
        """
        검색 결과의 카페 항목이 모두 대표카페인지 확인.
        각 ugcItem 중 cafe.naver.com 링크를 포함하는 항목에서
        대표카페 배지(SVG viewBox="0 0 20 15") 유무를 확인.
        비대표카페가 하나라도 있으면 False, 전부 대표카페이면 True(default).
        파워콘텐츠(광고) 항목(data-power-content-url 속성 보유)은 판정에서 제외.
        """
        try:
            items = soup.find_all('div', attrs={'data-template-id': 'ugcItem'})
            if not items:
                return True  # 결과 없으면 default(대표카페)
            for item in items:
                # 파워콘텐츠(광고) 항목은 대표카페 판정에서 제외
                if item.get('data-power-content-url'):
                    continue
                is_cafe = item.find('a', href=lambda h: h and 'cafe.naver.com' in h)
                if not is_cafe:
                    continue
                badge = item.find('svg', attrs={'viewbox': '0 0 20 15'})
                if not badge:
                    logging.info("[대표카페] 비대표카페 항목 발견 → is_main_cafe=False")
                    return False
        except Exception as e:
            logging.info(f"대표카페 확인 중 오류: {e}")
        return True

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

    def _is_driver_alive(self):
        """드라이버 세션이 살아있는지 확인"""
        if self._driver is None:
            return False
        try:
            _ = self._driver.current_url
            return True
        except Exception:
            return False

    def _init_driver(self):
        """Selenium WebDriver 초기화 (죽은 세션이면 재생성)"""
        if not self._is_driver_alive():
            # 죽은 드라이버 정리
            if self._driver is not None:
                try:
                    self._driver.quit()
                except Exception:
                    pass
                self._driver = None

            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_argument('--incognito')
            chrome_options.add_argument('--disable-application-cache')
            chrome_options.add_argument('--disable-cache')
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
        if not url or ('cafe.naver.com' not in url and 'blog.naver.com' not in url):
            return None, "유효하지 않은 URL"

        try:
            driver = self._init_driver()

            driver.get(url)
            time.sleep(1.5)  # alert 대기

            try:
                # JavaScript alert 확인 (카페 방식)
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()  # alert 닫기

                if '삭제' in alert_text or '변경' in alert_text or '존재하지 않' in alert_text:
                    return True, alert_text
                return False, None

            except NoAlertPresentException:
                # 블로그: alert 없이 페이지로 비공개/제한 표시
                if 'blog.naver.com' in url:
                    page_source = driver.page_source
                    if '비공개 블로그입니다' in page_source or '접근이 제한' in page_source:
                        return True, "비공개 블로그"
                return False, None

        except UnexpectedAlertPresentException:
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

    def analyze_keyword_layout(self, keyword: str) -> dict:
        """
        키워드 검색 결과 레이아웃 분석.
        상단/하단/단일 블록 구분, 카페별 순위, 발행일 반환.

        Returns:
            {
                'has_split_block': bool,
                'main_results': [
                    {'rank': 1, 'cafe_name': '씨씨앙', 'display_name': '컬처블룸',
                     'url': '...', 'block': 'head'|'body'|'single', 'published_at': '2026.02.03'},
                    ...
                ],
                'popular_results': [
                    {'rank': 1, 'cafe_name': '...', 'display_name': '...', 'url': '...', 'published_at': '...'},
                    ...
                ]
            }
        """
        import re
        from src.config import CAFE_URL_MAP

        result = {
            'has_split_block': False,
            'main_results': [],
            'popular_results': []
        }

        def get_block(element):
            node = element
            while node:
                classes = node.get('class') or []
                if '_fsolid_head' in classes:
                    return 'head'
                if '_fsolid_body' in classes:
                    return 'body'
                node = node.parent
            return 'single'

        def get_cafe_name(ugc_item):
            el = ugc_item.find('span', class_=lambda c: c and 'sds-comps-profile-info-title-text' in (
                c if isinstance(c, str) else ' '.join(c)))
            return el.get_text(strip=True) if el else None

        def get_slug_from_url(url: str) -> str:
            """cafe.naver.com/SLUG/... 에서 slug 추출"""
            if 'cafe.naver.com/' in url:
                return url.split('cafe.naver.com/')[1].split('/')[0].split('?')[0]
            return ''

        def get_display_name(cafe_name: str, url: str) -> str:
            """URL slug로 단축명 조회, 없으면 원래 카페명 반환"""
            slug = get_slug_from_url(url)
            return CAFE_URL_MAP.get(slug, cafe_name or '')

        def get_published_at(ugc_item) -> str:
            """ugcItem에서 발행일 추출 (YYYY.MM.DD 또는 상대시간)"""
            subtext = ugc_item.find('span', class_=lambda c: c and 'profile-info-subtext' in (
                c if isinstance(c, str) else ' '.join(c)))
            if not subtext:
                return ''
            text = subtext.get_text(strip=True)
            # YYYY.MM.DD. 형식
            m = re.search(r'(\d{4}\.\d{2}\.\d{2})\.?', text)
            if m:
                return m.group(1)
            # 상대시간 (N일 전, N시간 전, 어제 등)
            m2 = re.search(r'(\d+[일시간분]+\s*전|어제|오늘)', text)
            if m2:
                return m2.group(1)
            return text[:15]

        try:
            soup = self.get_search_results(keyword, delay=False)
            if not soup:
                logging.warning(f"analyze_keyword_layout: '{keyword}' 검색 결과 없음")
                return result

            # 상하단 구분 여부
            has_head = soup.find(class_=lambda c: c and '_fsolid_head' in (
                c if isinstance(c, str) else ' '.join(c)))
            result['has_split_block'] = has_head is not None

            # 인기글 섹션 추출
            popular_url_set = set()
            popular_items_raw = []
            for h_el in soup.find_all('div', class_=lambda c: c and 'sds-comps-header-title' in (
                    c if isinstance(c, str) else ' '.join(c))):
                h2 = h_el.find('h2')
                if not h2 or '인기글' not in h2.get_text():
                    continue
                section = h_el.parent.parent if h_el.parent else None
                if not section:
                    continue
                for a_tag in section.find_all('a', attrs={'data-heatmap-target': '.link'}):
                    href = a_tag.get('href', '')
                    if not href:
                        continue
                    norm_url = self.normalize_url(href)
                    if norm_url in popular_url_set:
                        continue
                    popular_url_set.add(norm_url)
                    item_el = a_tag.find_parent('div', attrs={'data-template-id': 'ugcItem'})
                    cafe_name = get_cafe_name(item_el) if item_el else None
                    published_at = get_published_at(item_el) if item_el else ''
                    popular_items_raw.append({
                        'cafe_name': cafe_name,
                        'display_name': get_display_name(cafe_name, href),
                        'url': norm_url,
                        'published_at': published_at,
                    })

            for idx, item in enumerate(popular_items_raw):
                result['popular_results'].append({'rank': idx + 1, **item})

            # 메인 결과: 인기글 섹션 제거 후 ugcItem 순서대로
            analysis_soup = copy.copy(soup)
            for h_el in analysis_soup.find_all('div', class_=lambda c: c and 'sds-comps-header-title' in (
                    c if isinstance(c, str) else ' '.join(c))):
                h2 = h_el.find('h2')
                if h2 and '인기글' in h2.get_text():
                    section = h_el.parent.parent if h_el.parent else None
                    if section:
                        section.decompose()
                    break

            rank = 1
            for ugc_item in analysis_soup.find_all('div', attrs={'data-template-id': 'ugcItem'}):
                if ugc_item.get('data-power-content-url'):
                    continue
                cafe_link = ugc_item.find('a', attrs={'data-heatmap-target': '.link'},
                                          href=lambda h: h and 'cafe.naver.com' in h)
                if not cafe_link:
                    cafe_link = ugc_item.find('a', href=lambda h: h and 'cafe.naver.com' in h)
                if not cafe_link:
                    continue
                href = cafe_link.get('href', '')
                cafe_name = get_cafe_name(ugc_item)
                result['main_results'].append({
                    'rank': rank,
                    'cafe_name': cafe_name,
                    'display_name': get_display_name(cafe_name, href),
                    'url': self.normalize_url(href),
                    'block': get_block(ugc_item),
                    'published_at': get_published_at(ugc_item),
                })
                rank += 1

            logging.info(
                f"레이아웃 분석 완료 '{keyword}': split={result['has_split_block']}, "
                f"메인={len(result['main_results'])}개, 인기글={len(result['popular_results'])}개"
            )
        except Exception as e:
            logging.error(f"레이아웃 분석 실패 '{keyword}': {e}")

        return result

    def get_layout_metrics(self, keyword: str, target_urls: Optional[list] = None) -> dict:
        """
        네이버 검색결과 페이지에서 레이아웃 측정값 반환.
        Selenium으로 페이지를 렌더링하여 요소 위치를 측정.

        Args:
            keyword:      검색 키워드 (페이지 로딩에 사용)
            target_urls:  내 글 URL 목록 (정규화 후 비교). None이면 글 단위 측정 생략.

        Returns:
            {
                'has_split_block': bool or None,  -- _fsolid_head 존재 여부
                'first_cafe_y_pct': float or None,  -- 첫 카페글 Y위치 %
                'url_metrics': {
                    'https://cafe.naver.com/xxx/123': {
                        'block_position': 'head' or 'body' or None,  -- 글이 속한 블록
                        'post_y_pct': float or None,  -- 글 Y위치 %
                    },
                    ...
                }
            }

        Returns (on error):
            {
                'has_split_block': None,
                'first_cafe_y_pct': None,
                'url_metrics': {}
            }
        """
        if target_urls is None:
            target_urls = []

        result = {
            'has_split_block': None,
            'first_cafe_y_pct': None,
            'url_metrics': {}
        }

        try:
            # 1. Selenium 드라이버 초기화
            driver = self._init_driver()
            if driver is None:
                logging.warning(f"레이아웃 측정 '{keyword}': 드라이버 초기화 실패")
                return result

            # 2. 검색 페이지 로딩
            search_url = f"https://search.naver.com/search.naver?query={keyword}"
            driver.get(search_url)
            time.sleep(2.5)  # 렌더링 대기

            # 3. 페이지 높이 확인
            scroll_height = driver.execute_script("return document.body.scrollHeight")
            if scroll_height <= 0:
                logging.warning(f"레이아웃 측정 '{keyword}': scrollHeight <= 0 (페이지 미렌더링)")
                return result

            # 4. 키워드 단위: has_split_block (상하단 구분)
            has_split_block = driver.execute_script("""
                return document.querySelector('._fsolid_head') !== null;
            """)
            result['has_split_block'] = has_split_block

            # 5. 키워드 단위: first_cafe_y_pct (첫 카페글 Y위치)
            first_cafe_y_pct = driver.execute_script("""
                var pageHeight = document.body.scrollHeight;
                // _fsolid_head, _fsolid_body 각각의 링크 중 cafe.naver.com URL 찾기
                var headLinks = document.querySelectorAll('._fsolid_head a[href*="cafe.naver.com"]');
                var bodyLinks = document.querySelectorAll('._fsolid_body a[href*="cafe.naver.com"]');
                var allCafeLinks = Array.from(headLinks).concat(Array.from(bodyLinks));

                if (allCafeLinks.length > 0) {
                    var rect = allCafeLinks[0].getBoundingClientRect();
                    var top = rect.top + window.scrollY;
                    return Math.round(top / pageHeight * 1000) / 10;
                }
                return null;
            """)
            result['first_cafe_y_pct'] = first_cafe_y_pct

            # 6. 글 단위 측정: 정규화된 target_urls에 대해 block_position, post_y_pct 측정
            if target_urls:
                # JavaScript로 한 번에 모든 링크 측정 (성능상 유리)
                all_links_data = driver.execute_script("""
                    var pageHeight = document.body.scrollHeight;
                    var linksData = [];

                    function getBlockPosition(el) {
                        var cur = el;
                        while (cur) {
                            var cls = cur.className || '';
                            if (cls.indexOf('_fsolid_head') !== -1) return 'head';
                            if (cls.indexOf('_fsolid_body') !== -1) return 'body';
                            cur = cur.parentElement;
                        }
                        return 'single';
                    }

                    function normalizeUrl(url) {
                        // ?: 쿼리 파라미터 제거
                        var base = url.split('?')[0];
                        // JWT 토큰(=token) 제거
                        if ((base.indexOf('cafe.naver.com') !== -1 || base.indexOf('blog.naver.com') !== -1) && base.indexOf('=') !== -1) {
                            base = base.split('=')[0];
                        }
                        return base;
                    }

                    // 모든 a 태그 순회
                    var allLinks = document.querySelectorAll('a[href*="cafe.naver.com"], a[href*="blog.naver.com"]');
                    allLinks.forEach(function(link) {
                        var href = link.getAttribute('href') || '';
                        var rect = link.getBoundingClientRect();
                        var top = rect.top + window.scrollY;
                        var yPct = Math.round(top / pageHeight * 1000) / 10;
                        var blockPos = getBlockPosition(link);

                        linksData.push({
                            url: normalizeUrl(href),
                            block_position: blockPos,
                            post_y_pct: yPct > 0 ? yPct : null
                        });
                    });

                    return linksData;
                """)

                # 측정된 링크와 target_urls 매칭
                for link_data in all_links_data:
                    link_url = link_data['url']
                    for target_url in target_urls:
                        if self.normalize_url(target_url) == self.normalize_url(link_url):
                            result['url_metrics'][target_url] = {
                                'block_position': link_data['block_position'],
                                'post_y_pct': link_data['post_y_pct']
                            }
                            break

            logging.info(f"레이아웃 측정 완료 '{keyword}': has_split={result['has_split_block']}, first_pct={result['first_cafe_y_pct']}")
            return result

        except Exception as e:
            logging.warning(f"레이아웃 측정 예외 '{keyword}': {e}")
            return result