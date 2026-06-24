"""
네이버 키워드 노출 모니터링 - GUI 버전
제품별 선택 후 모니터링 실행 (완료 후 즉시 재실행)
"""

import sys
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import logging

from src.scraper import NaverScraper
from src.monitor import KeywordMonitor
from src.blog_monitor import BlogMonitor
from src.db_client import DatabaseClient
from src.google_sheets import GoogleSheetsClient
from src.config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_TABLE,
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_SHEETS_ID, GOOGLE_SHEETS_GID,
    KEYWORD_LIST_SHEETS_ID, KEYWORD_LIST_SHEETS_GID,
    BLOG_SHEETS_ID, BLOG_SHEETS_GID,
    BLOG_KEYWORD_LIST_SHEETS_ID, BLOG_KEYWORD_LIST_SHEETS_GID,
    CAFE_RANKING_SHEETS_ID, CAFE_RANKING_SHEETS_GID,
)


class TextHandler(logging.Handler):
    """로그를 tkinter Text 위젯에 출력하는 핸들러"""

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record) + '\n'
        self.text_widget.after(0, self._append, msg)

    def _append(self, msg):
        self.text_widget.configure(state='normal')
        self.text_widget.insert(tk.END, msg)
        self.text_widget.see(tk.END)
        self.text_widget.configure(state='disabled')


class MonitoringApp:
    def __init__(self, root):
        self.root = root
        self.root.title("키워드 노출 모니터링")
        self.root.resizable(False, False)

        self._loop_active = False  # 반복 실행 중 여부
        self._stopping = False     # 종료 중 여부
        self._analysis_running = False

        self._build_ui()
        self._setup_logging()
        self._load_products()

    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)

        # Tab 1: 카페/블로그 순찰
        tab_monitor = tk.Frame(self.notebook)
        self.notebook.add(tab_monitor, text='  카페/블로그 순찰  ')
        self._build_monitor_tab(tab_monitor)

        # Tab 2: 레이아웃 분석
        tab_analysis = tk.Frame(self.notebook)
        self.notebook.add(tab_analysis, text='  레이아웃 분석  ')
        self._build_analysis_tab(tab_analysis)

    # ──────────────────────────────────────────────────
    # Tab 1: 카페/블로그 순찰
    # ──────────────────────────────────────────────────
    def _build_monitor_tab(self, parent):
        pad = {'padx': 12, 'pady': 6}

        tk.Label(parent, text="네이버 키워드 노출 모니터링",
                 font=("맑은 고딕", 14, "bold")).pack(**pad)

        # 순찰 유형 선택
        self.mode_var = tk.StringVar(value='카페')
        mode_frame = tk.Frame(parent)
        mode_frame.pack(fill='x', padx=12, pady=(6, 0))
        tk.Label(mode_frame, text='순찰 유형:', font=('맑은 고딕', 10)).pack(side='left', padx=(0, 8))
        tk.Radiobutton(mode_frame, text='카페', variable=self.mode_var,
                       value='카페', command=self._on_mode_change,
                       font=('맑은 고딕', 10)).pack(side='left', padx=4)
        tk.Radiobutton(mode_frame, text='블로그', variable=self.mode_var,
                       value='블로그', command=self._on_mode_change,
                       font=('맑은 고딕', 10)).pack(side='left', padx=4)

        # 제품 선택
        frame = tk.Frame(parent)
        frame.pack(fill='x', **pad)
        tk.Label(frame, text="제품 선택:", font=("맑은 고딕", 10)).pack(side='left', padx=(0, 8))
        self.product_var = tk.StringVar(value="전체")
        self.product_combo = ttk.Combobox(
            frame, textvariable=self.product_var,
            values=["전체"],
            state='readonly', font=("맑은 고딕", 10), width=20
        )
        self.product_combo.pack(side='left')

        # 순찰 간격 + 시트 동기화
        option_frame = tk.Frame(parent)
        option_frame.pack(fill='x', padx=12, pady=(0, 4))
        tk.Label(option_frame, text="순찰 간격(분):", font=("맑은 고딕", 10)).pack(side='left', padx=(0, 4))
        self.interval_var = tk.StringVar(value="0")
        vcmd = (self.root.register(lambda v: v.isdigit() or v == ""), '%P')
        self.interval_entry = tk.Entry(
            option_frame, textvariable=self.interval_var,
            validate='key', validatecommand=vcmd,
            font=("맑은 고딕", 10), width=5
        )
        self.interval_entry.pack(side='left', padx=(0, 16))
        self.sync_var = tk.BooleanVar(value=True)
        self.sync_check = tk.Checkbutton(
            option_frame, text="시트 동기화", variable=self.sync_var,
            font=("맑은 고딕", 10)
        )
        self.sync_check.pack(side='left')

        # 시작/중지 버튼
        self.run_btn = tk.Button(
            parent, text="모니터링 시작", font=("맑은 고딕", 11, "bold"),
            bg="#2196F3", fg="white", activebackground="#1565C0", activeforeground="white",
            command=self._on_toggle, height=2, width=20
        )
        self.run_btn.pack(pady=10)

        # 진행 표시줄
        self.progress = ttk.Progressbar(parent, mode='indeterminate', length=420)
        self.progress.pack(padx=12, pady=(0, 6))

        # 로그 출력창
        log_frame = tk.LabelFrame(parent, text="실행 로그", font=("맑은 고딕", 10))
        log_frame.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        self.log_area = scrolledtext.ScrolledText(
            log_frame, state='disabled', height=20, width=70,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white"
        )
        self.log_area.pack(fill='both', expand=True, padx=4, pady=4)

    # ──────────────────────────────────────────────────
    # Tab 2: 카페 랭킹 분석
    # ──────────────────────────────────────────────────
    def _build_analysis_tab(self, parent):
        # 옵션 행
        opt_frame = tk.Frame(parent)
        opt_frame.pack(fill='x', padx=12, pady=10)

        tk.Label(opt_frame, text="제품 선택:", font=('맑은 고딕', 10)).pack(side='left', padx=(0, 6))
        self.ranking_product_var = tk.StringVar(value='전체')
        self.ranking_product_combo = ttk.Combobox(
            opt_frame, textvariable=self.ranking_product_var,
            values=['전체'], state='readonly', font=('맑은 고딕', 10), width=18
        )
        self.ranking_product_combo.pack(side='left', padx=(0, 16))

        self.ranking_sync_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            opt_frame, text="분석 후 시트 동기화", variable=self.ranking_sync_var,
            font=('맑은 고딕', 10)
        ).pack(side='left', padx=(0, 16))

        self.ranking_btn = tk.Button(
            opt_frame, text="랭킹 분석 실행", font=('맑은 고딕', 10, 'bold'),
            bg='#4CAF50', fg='white', activebackground='#388E3C',
            command=self._on_ranking_start, width=14
        )
        self.ranking_btn.pack(side='left')

        self.ranking_status_var = tk.StringVar(value='')
        tk.Label(opt_frame, textvariable=self.ranking_status_var,
                 font=('맑은 고딕', 9), fg='#888888').pack(side='left', padx=10)

        # 진행 표시줄
        self.ranking_progress = ttk.Progressbar(parent, mode='indeterminate', length=420)
        self.ranking_progress.pack(padx=12, pady=(0, 4))

        # 로그 출력창
        log_frame = tk.LabelFrame(parent, text="실행 로그", font=("맑은 고딕", 10))
        log_frame.pack(fill='both', expand=True, padx=12, pady=(0, 12))

        self.ranking_log = scrolledtext.ScrolledText(
            log_frame, state='disabled', height=26, width=70,
            font=('Consolas', 9), bg='#1e1e1e', fg='#d4d4d4',
            insertbackground='white'
        )
        self.ranking_log.pack(fill='both', expand=True, padx=4, pady=4)

    def _on_ranking_start(self):
        if self._analysis_running:
            return

        label = self.ranking_product_var.get()
        products = None if label == '전체' else [label]

        self._analysis_running = True
        self.ranking_btn.config(state='disabled', bg='#888888')
        self.ranking_status_var.set('분석 중...')
        self.ranking_progress.start(10)

        threading.Thread(
            target=self._run_ranking_analysis,
            args=(products,),
            daemon=True
        ).start()

    def _run_ranking_analysis(self, products):
        def log(msg):
            self.ranking_log.after(0, self._ranking_log_append, msg)

        try:
            # DB 연결
            db = DatabaseClient(
                host=DB_HOST, port=DB_PORT,
                user=DB_USER, password=DB_PASSWORD,
                database=DB_NAME, table=DB_TABLE
            )
            if not db.connect():
                log("DB 연결 실패")
                return

            keywords = db.get_keywords_for_ranking_analysis(products)
            log(f"분석 대상 키워드 {len(keywords)}개")

            scraper = NaverScraper()
            total = len(keywords)
            for idx, kw in enumerate(keywords, 1):
                keyword_id = kw['keyword_id']
                keyword = kw['keyword']
                log(f"[{idx}/{total}] '{keyword}' 분석 중...")

                try:
                    data = scraper.analyze_keyword_layout(keyword)
                    layout_label = '상하단구분' if data['has_split_block'] else '단일'

                    db.replace_cafe_ranking(
                        keyword_id=keyword_id,
                        has_split_block=data['has_split_block'],
                        main_results=data['main_results'],
                        popular_results=data['popular_results']
                    )

                    # 로그 요약
                    main = data['main_results']
                    summary_parts = []
                    for r in main[:4]:
                        block = {'head': '상단', 'body': '하단', 'single': ''}.get(r['block'], '')
                        name = r['cafe_name'] or '?'
                        summary_parts.append(f"{r['rank']}위 {name}" + (f"({block})" if block else ''))
                    popular = data['popular_results']
                    pop_part = f" | 인기글 {len(popular)}개" if popular else ''
                    log(f"  [{layout_label}] {', '.join(summary_parts)}{' ...' if len(main) > 4 else ''}{pop_part}")

                except Exception as e:
                    log(f"  '{keyword}' 분석 실패: {e}")

            log("─" * 50)
            log("DB 저장 완료")

            # 시트 동기화
            if self.ranking_sync_var.get():
                if not CAFE_RANKING_SHEETS_ID:
                    log("CAFE_RANKING_SHEETS_ID 미설정 — 시트 동기화 건너뜀")
                else:
                    log("구글 시트 동기화 중...")
                    try:
                        ranking_client = GoogleSheetsClient(
                            credentials_path=GOOGLE_CREDENTIALS_PATH,
                            spreadsheet_id=CAFE_RANKING_SHEETS_ID,
                            sheet_gid=CAFE_RANKING_SHEETS_GID
                        )
                        if ranking_client.connect():
                            headers, rows = db.get_cafe_ranking_for_sheet()
                            if rows:
                                ranking_client.sync_patrol_logs(headers, rows)
                                log(f"시트 동기화 완료 ({len(rows)}개 키워드) ✓")
                            else:
                                log("동기화할 데이터 없음")
                        else:
                            log("카페랭킹 시트 연결 실패")
                    except Exception as e:
                        log(f"시트 동기화 오류: {e}")

            db.disconnect()
            log("분석 완료")

        except Exception as e:
            log(f"오류: {e}")
        finally:
            self.root.after(0, self._ranking_done)

    def _ranking_log_append(self, msg):
        self.ranking_log.configure(state='normal')
        self.ranking_log.insert(tk.END, msg + '\n')
        self.ranking_log.see(tk.END)
        self.ranking_log.configure(state='disabled')

    def _ranking_done(self):
        self._analysis_running = False
        self.ranking_btn.config(state='normal', bg='#4CAF50')
        self.ranking_status_var.set('')
        self.ranking_progress.stop()

    # ──────────────────────────────────────────────────
    # 공통 / 순찰 탭 로직
    # ──────────────────────────────────────────────────
    def _setup_logging(self):
        handler = TextHandler(self.log_area)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)

    def _on_mode_change(self):
        logging.info(f"순찰 모드 변경: {self.mode_var.get()}")
        self._load_products()

    def _load_products(self):
        def _fetch():
            try:
                db = DatabaseClient(
                    host=DB_HOST, port=DB_PORT,
                    user=DB_USER, password=DB_PASSWORD,
                    database=DB_NAME, table=DB_TABLE
                )
                if db.connect():
                    mode = self.mode_var.get()
                    if mode == '카페':
                        products = db.get_distinct_products()
                    else:
                        products = db.get_distinct_blog_products()
                    db.disconnect()
                    self.root.after(0, self._set_products, products)
                else:
                    logging.warning("DB 연결 실패 — 제품 목록을 가져올 수 없습니다.")
            except Exception as e:
                logging.error(f"제품 목록 로드 오류: {e}")

        threading.Thread(target=_fetch, daemon=True).start()

    def _set_products(self, products):
        options = ["전체"] + products
        self.product_combo['values'] = options
        self.product_var.set("전체")
        # 랭킹 분석 탭 드롭다운도 동기화 (카페 제품 목록 공유)
        self.ranking_product_combo['values'] = options
        if self.ranking_product_var.get() not in options:
            self.ranking_product_var.set("전체")

    def _on_toggle(self):
        if self._loop_active:
            self._loop_active = False
            self._stopping = True
            self.run_btn.config(
                text="종료 중...", state='disabled',
                bg="#FF9800", activebackground="#E65100"
            )
            logging.info("종료 요청됨 — 현재 회차 완료 후 프로그램을 종료합니다.")
        else:
            label = self.product_var.get()
            self._products = None if label == "전체" else [label]
            self._loop_active = True
            self._stopping = False
            self.product_combo.config(state='disabled')
            self.interval_entry.config(state='disabled')
            self.run_btn.config(
                text="모니터링 중지", bg="#F44336",
                activebackground="#B71C1C"
            )
            self.progress.start(10)
            self._clear_log()
            logging.info(f"선택된 제품: {label} — 반복 실행 시작")
            self._start_one_cycle()

    def _start_one_cycle(self):
        thread = threading.Thread(
            target=self._run_monitoring, args=(self._products,), daemon=True
        )
        thread.start()

    def _clear_log(self):
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)
        self.log_area.configure(state='disabled')

    def _run_monitoring(self, products):
        try:
            logging.info("─" * 50)
            logging.info("DB 연결 중...")
            db_client = DatabaseClient(
                host=DB_HOST, port=DB_PORT,
                user=DB_USER, password=DB_PASSWORD,
                database=DB_NAME, table=DB_TABLE
            )
            if not db_client.connect():
                logging.error("DB 연결 실패. 모니터링을 종료합니다.")
                self._loop_active = False
                return

            mode = self.mode_var.get()
            scraper = NaverScraper()

            if mode == '카페':
                monitor = KeywordMonitor(scraper, db_client)
                logging.info("카페 키워드 모니터링 시작...")
                results = monitor.monitor_keywords(products=products)
                logging.info(f"카페 회차 완료 (처리 {len(results)}건)")

                if self.sync_var.get():
                    logging.info("[1/2] 키워드순찰 시트 동기화 중...")
                    patrol_client = GoogleSheetsClient(
                        credentials_path=GOOGLE_CREDENTIALS_PATH,
                        spreadsheet_id=GOOGLE_SHEETS_ID,
                        sheet_gid=GOOGLE_SHEETS_GID
                    )
                    if patrol_client.connect():
                        headers, rows = db_client.get_all_patrol_logs()
                        if rows:
                            patrol_client.sync_patrol_logs(headers, rows)
                            logging.info("키워드순찰 시트 동기화 완료 ✓")
                        else:
                            logging.warning("동기화할 데이터 없음")
                    else:
                        logging.warning("키워드순찰 시트 연결 실패 — 동기화 건너뜀")

                    logging.info("[2/2] 키워드목록 시트 동기화 중...")
                    kl_client = GoogleSheetsClient(
                        credentials_path=GOOGLE_CREDENTIALS_PATH,
                        spreadsheet_id=KEYWORD_LIST_SHEETS_ID,
                        sheet_gid=KEYWORD_LIST_SHEETS_GID
                    )
                    if kl_client.connect():
                        kl_headers, kl_rows = db_client.get_keyword_list_from_view()
                        if kl_rows:
                            kl_client.sync_patrol_logs(kl_headers, kl_rows)
                            logging.info("키워드목록 시트 동기화 완료 ✓")
                        else:
                            logging.warning("동기화할 데이터 없음")
                    else:
                        logging.warning("키워드목록 시트 연결 실패 — 동기화 건너뜀")
                else:
                    logging.info("시트 동기화 비활성화 — 건너뜀")

            else:
                monitor = BlogMonitor(scraper, db_client)
                logging.info("블로그 포스트 모니터링 시작...")
                results = monitor.monitor_blog_posts(products=products)
                logging.info(f"블로그 회차 완료 (처리 {len(results)}건)")

                if self.sync_var.get():
                    if BLOG_SHEETS_ID and BLOG_SHEETS_GID:
                        logging.info("[1/2] 블로그순찰 시트 동기화 중...")
                        blog_client = GoogleSheetsClient(
                            credentials_path=GOOGLE_CREDENTIALS_PATH,
                            spreadsheet_id=BLOG_SHEETS_ID,
                            sheet_gid=BLOG_SHEETS_GID
                        )
                        if blog_client.connect():
                            headers, rows = db_client.get_all_blog_patrol_logs()
                            if rows:
                                blog_client.sync_patrol_logs(headers, rows)
                                logging.info("블로그순찰 시트 동기화 완료 ✓")
                            else:
                                logging.warning("블로그 동기화할 데이터 없음")
                        else:
                            logging.warning("블로그순찰 시트 연결 실패 — 동기화 건너뜀")
                    else:
                        logging.warning("BLOG_SHEETS_ID 또는 BLOG_SHEETS_GID가 설정되지 않음 — 동기화 건너뜀")

                    logging.info("[2/2] 블로그 키워드목록 시트 동기화 중...")
                    blog_kl_client = GoogleSheetsClient(
                        credentials_path=GOOGLE_CREDENTIALS_PATH,
                        spreadsheet_id=BLOG_KEYWORD_LIST_SHEETS_ID,
                        sheet_gid=BLOG_KEYWORD_LIST_SHEETS_GID
                    )
                    if blog_kl_client.connect():
                        kl_headers, kl_rows = db_client.get_blog_keyword_list_from_view()
                        if kl_rows:
                            blog_kl_client.sync_patrol_logs(kl_headers, kl_rows)
                            logging.info("블로그 키워드목록 시트 동기화 완료 ✓")
                        else:
                            logging.warning("블로그 키워드목록 동기화할 데이터 없음")
                    else:
                        logging.warning("블로그 키워드목록 시트 연결 실패 — 동기화 건너뜀")
                else:
                    logging.info("시트 동기화 비활성화 — 건너뜀")

            db_client.disconnect()

        except Exception as e:
            logging.error(f"모니터링 중 오류 발생: {e}")
        finally:
            self.root.after(0, self._on_cycle_done)

    def _on_cycle_done(self):
        if self._loop_active:
            interval_minutes = int(self.interval_var.get() or 0)
            if interval_minutes > 0:
                logging.info(f"다음 회차까지 {interval_minutes}분 대기 중...")
                self._wait_and_restart(interval_minutes * 60)
            else:
                logging.info("다음 회차 즉시 시작...")
                self._start_one_cycle()
        else:
            self.progress.stop()
            self.interval_entry.config(state='normal')
            logging.info("프로그램을 종료합니다.")
            self.root.after(500, self._exit_app)

    def _wait_and_restart(self, remaining_seconds):
        if not self._loop_active:
            self.progress.stop()
            self.interval_entry.config(state='normal')
            logging.info("프로그램을 종료합니다.")
            self.root.after(500, self._exit_app)
            return
        if remaining_seconds <= 0:
            logging.info("대기 완료 — 다음 회차 시작...")
            self._start_one_cycle()
            return
        mins, secs = divmod(remaining_seconds, 60)
        self.run_btn.config(text=f"중지 ({mins:02d}:{secs:02d} 후 재시작)")
        self.root.after(1000, self._wait_and_restart, remaining_seconds - 1)

    def _exit_app(self):
        self.root.destroy()
        sys.exit(0)


def main():
    root = tk.Tk()
    MonitoringApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
