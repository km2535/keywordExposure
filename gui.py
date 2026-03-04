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
from src.db_client import DatabaseClient
from src.google_sheets import GoogleSheetsClient
from src.config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_TABLE,
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_SHEETS_ID, GOOGLE_SHEETS_GID,
    KEYWORD_LIST_SHEETS_ID, KEYWORD_LIST_SHEETS_GID,
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

        # 시트 동기화 체크박스
        self.sync_var = tk.BooleanVar(value=True)
        self.sync_check = tk.Checkbutton(
            self.root, text="시트 동기화", variable=self.sync_var,
            font=("맑은 고딕", 10)
        )
        self.sync_check.pack(pady=(0, 4))

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

    def _load_products(self):
        """DB에서 제품 목록을 불러와 드롭다운에 채움"""
        def _fetch():
            try:
                db = DatabaseClient(
                    host=DB_HOST, port=DB_PORT,
                    user=DB_USER, password=DB_PASSWORD,
                    database=DB_NAME, table=DB_TABLE
                )
                if db.connect():
                    products = db.get_distinct_products()
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

            # 시트 클라이언트는 넘기지 않고, 모니터링 완료 후 sync_var를 확인해 직접 동기화
            scraper = NaverScraper()
            monitor = KeywordMonitor(scraper, db_client)

            logging.info("키워드 모니터링 시작...")
            results = monitor.monitor_keywords(products=products)
            logging.info(f"회차 완료 (처리 {len(results)}건)")

            # 키워드 처리 완료 후 체크박스 상태를 읽어 동기화 여부 결정
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

            db_client.disconnect()

        except Exception as e:
            logging.error(f"모니터링 중 오류 발생: {e}")
        finally:
            self.root.after(0, self._on_cycle_done)

    def _on_cycle_done(self):
        if self._loop_active:
            # 즉시 다음 회차 실행
            logging.info("다음 회차 즉시 시작...")
            self._start_one_cycle()
        else:
            # 종료 완료 — 프로그램 종료
            self.progress.stop()
            logging.info("프로그램을 종료합니다.")
            self.root.after(500, self._exit_app)

    def _exit_app(self):
        self.root.destroy()
        sys.exit(0)


def main():
    root = tk.Tk()
    MonitoringApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
