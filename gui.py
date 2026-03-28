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

        self._build_ui()
        self._setup_logging()
        self._load_products()

    def _build_ui(self):
        pad = {'padx': 12, 'pady': 6}

        # 제목
        tk.Label(self.root, text="네이버 키워드 노출 모니터링",
                 font=("맑은 고딕", 14, "bold")).pack(**pad)

        # 순찰 유형 선택 (RadioButton: 카페/블로그)
        self.mode_var = tk.StringVar(value='카페')
        mode_frame = tk.Frame(self.root)
        mode_frame.pack(fill='x', padx=12, pady=(6, 0))
        tk.Label(mode_frame, text='순찰 유형:', font=('맑은 고딕', 10)).pack(side='left', padx=(0, 8))
        tk.Radiobutton(mode_frame, text='카페', variable=self.mode_var,
                       value='카페', command=self._on_mode_change,
                       font=('맑은 고딕', 10)).pack(side='left', padx=4)
        tk.Radiobutton(mode_frame, text='블로그', variable=self.mode_var,
                       value='블로그', command=self._on_mode_change,
                       font=('맑은 고딕', 10)).pack(side='left', padx=4)

        # 제품 선택 드롭다운
        frame = tk.Frame(self.root)
        frame.pack(fill='x', **pad)

        tk.Label(frame, text="제품 선택:", font=("맑은 고딕", 10)).pack(side='left', padx=(0, 8))

        self.product_var = tk.StringVar(value="전체")
        self.product_combo = ttk.Combobox(
            frame, textvariable=self.product_var,
            values=["전체"],
            state='readonly', font=("맑은 고딕", 10), width=20
        )
        self.product_combo.pack(side='left')

        # 순찰 간격 + 시트 동기화 (같은 줄)
        option_frame = tk.Frame(self.root)
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
            self.root, text="모니터링 시작", font=("맑은 고딕", 11, "bold"),
            bg="#2196F3", fg="white", activebackground="#1565C0", activeforeground="white",
            command=self._on_toggle, height=2, width=20
        )
        self.run_btn.pack(pady=10)

        # 진행 표시줄
        self.progress = ttk.Progressbar(self.root, mode='indeterminate', length=420)
        self.progress.pack(padx=12, pady=(0, 6))

        # 로그 출력창
        log_frame = tk.LabelFrame(self.root, text="실행 로그", font=("맑은 고딕", 10))
        log_frame.pack(fill='both', expand=True, padx=12, pady=(0, 12))

        self.log_area = scrolledtext.ScrolledText(
            log_frame, state='disabled', height=20, width=70,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white"
        )
        self.log_area.pack(fill='both', expand=True, padx=4, pady=4)

    def _setup_logging(self):
        handler = TextHandler(self.log_area)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)

    def _on_mode_change(self):
        """순찰 유형 변경 시 제품 드롭다운 재로드"""
        logging.info(f"순찰 모드 변경: {self.mode_var.get()}")
        self._load_products()

    def _load_products(self):
        """DB에서 제품 목록을 불러와 드롭다운에 채움 (모드에 따라 카페/블로그 제품 구분)"""
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
                    else:  # 블로그
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

    def _on_toggle(self):
        if self._loop_active:
            # 중지 요청 — 현재 실행 중인 회차가 끝난 후 프로그램 종료
            self._loop_active = False
            self._stopping = True
            self.run_btn.config(
                text="종료 중...", state='disabled',
                bg="#FF9800", activebackground="#E65100"
            )
            logging.info("종료 요청됨 — 현재 회차 완료 후 프로그램을 종료합니다.")
        else:
            # 시작
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
                # ===== 카페 모드 =====
                monitor = KeywordMonitor(scraper, db_client)
                logging.info("카페 키워드 모니터링 시작...")
                results = monitor.monitor_keywords(products=products)
                logging.info(f"카페 회차 완료 (처리 {len(results)}건)")

                # 카페 모드 시트 동기화
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
                # ===== 블로그 모드 =====
                monitor = BlogMonitor(scraper, db_client)
                logging.info("블로그 포스트 모니터링 시작...")
                results = monitor.monitor_blog_posts(products=products)
                logging.info(f"블로그 회차 완료 (처리 {len(results)}건)")

                # 블로그 모드 시트 동기화
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
            # 종료 완료 — 프로그램 종료
            self.progress.stop()
            self.interval_entry.config(state='normal')
            logging.info("프로그램을 종료합니다.")
            self.root.after(500, self._exit_app)

    def _wait_and_restart(self, remaining_seconds):
        """남은 초를 카운트다운하며 다음 회차 대기"""
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
