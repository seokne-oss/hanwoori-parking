import time
import os
import re
import requests
import sys
from datetime import datetime, timedelta, timezone

# 윈도우 터미널 한글 깨짐 방지
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 3.7 미만 대응 (필요시)
        import codecs
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

# --- 설정 및 환경 변수 ---
FLASK_SERVER_URL = os.environ.get("FLASK_SERVER_URL", "http://127.0.0.1:5000")
RUN_ONCE = os.environ.get("RUN_ONCE", "true").lower() == "true"
NICEPARK_ID = os.environ.get("NICEPARK_ID")
NICEPARK_PW = os.environ.get("NICEPARK_PW")
# GitHub Action 버전은 항상 헤드리스로 실행되며 자동 로그인을 시도합니다.

# --- 로그 파일 설정 ---
class TeeLogger:
    """stdout 출력을 콘솔과 파일에 동시에 기록합니다."""
    def __init__(self, filepath):
        self._terminal = sys.stdout
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self._log = open(filepath, 'a', encoding='utf-8')

    def write(self, message):
        self._terminal.write(message)
        self._log.write(message)
        self._log.flush()

    def flush(self):
        self._terminal.flush()
        self._log.flush()

    def close(self):
        self._log.close()

_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
_log_path = os.path.join(_log_dir, f"bot_{datetime.now().strftime('%Y%m%d')}.log")
sys.stdout = TeeLogger(_log_path)

def reset_to_discount_page(driver):
    """'검색된 차량 없음' 등 오류 후 '할인적용' 메뉴를 클릭하여 입력 화면을 초기화합니다."""
    try:
        menu_label = driver.find_element(By.ID, "mf_wfm_header_firstMenuGen_0_menu1_label")
        menu_link = menu_label.find_element(By.TAG_NAME, "a")
        driver.execute_script("arguments[0].click();", menu_link)
        time.sleep(1.2)
        print("   [초기화] '할인적용' 메뉴 클릭 → 화면 초기화 완료")
    except Exception as e:
        print(f"   [주의] 화면 초기화(할인적용 메뉴) 실패: {e}")

def clear_input_field(driver):
    """차량번호 입력 필드를 가상 키패드의 지우기 버튼을 사용하여 초기화합니다."""
    try:
        for _ in range(4):
            try:
                backspace_btn = driver.find_element(By.XPATH, "//input[@title='한 글자씩 삭제' or contains(@class, 'carNumBtn')]")
                if backspace_btn.is_displayed():
                    driver.execute_script("arguments[0].click();", backspace_btn)
                    time.sleep(0.2)
                else:
                    break
            except:
                break
        print("   [조치] 가상 키패드 지우기 버튼을 통해 입력 필드 초기화 완료")
    except Exception as e:
        print(f"   [오류] 입력 필드 초기화 실패: {e}")

def close_all_overlays(driver):
    """차량 처리 전 남아있는 모든 오버레이/레이어를 JS로 강제로 닫습니다.
    첫 번째 차량 처리 후 carListLayer가 active 상태로 잔류하는 버그 방지."""
    try:
        driver.execute_script("""
            var carLayer = document.getElementById('mf_wfm_body_carListLayer');
            if (carLayer) {
                carLayer.classList.remove('active');
                carLayer.style.display = 'none';
                carLayer.style.visibility = 'hidden';
            }
            ['_modal', '__modal', '___processbar2', '___processbar2_1'].forEach(function(id) {
                var el = document.getElementById(id);
                if (el) { el.style.display = 'none'; el.style.visibility = 'hidden'; }
            });
        """)
        print("   [정리] 잔류 오버레이/레이어 강제 초기화 완료")
    except Exception as e:
        print(f"   [주의] 오버레이 초기화 오류: {e}")

def extract_hhmm(text):
    """텍스트에서 HH:MM 형식의 시간만 안전하게 추출합니다.
    '2024-01-15 10:30:00' → '10:30' 처럼 긴 문자열도 처리."""
    if not text:
        return None
    match = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)(?::\d{2})?\b', text)
    return f"{match.group(1).zfill(2)}:{match.group(2)}" if match else None

def click_yes_button(driver, timeout=3):
    """WebSquare 커스텀 팝업의 '예' 버튼을 방해 요소 제거 후 다각도로 클릭 시도합니다."""
    try:
        # 1. 클릭 방해 요소(오버레이, 로딩바) 강제 숨김
        overlays = ["_modal", "__modal", "___processbar2", "___processbar2_1"]
        for ov_id in overlays:
            try:
                driver.execute_script(f"if(document.getElementById('{ov_id}')) document.getElementById('{ov_id}').style.display='none';")
                driver.execute_script(f"if(document.getElementById('{ov_id}')) document.getElementById('{ov_id}').style.visibility='hidden';")
            except: pass
            
        # 2. 버튼 탐색용 셀렉터 (사용자 캡처 정보 적극 반영)
        yes_selectors = [
            (By.CSS_SELECTOR, "input[id*='_confirm'][id*='_btn_yes']"),
            (By.XPATH, "//input[contains(@class, 'btn_cm') and (contains(@value, '예') or contains(@value, '확인'))]"),
            (By.XPATH, "//*[contains(@class, 'w2window')]//input[contains(@value, '예') or contains(@value, '확인')]"),
            (By.CSS_SELECTOR, "input[id*='_btn_yes'], input[id*='_btn_confirm']"),
            (By.CSS_SELECTOR, ".btn_cm.pt"),

        ]
        
        # 3. 버튼 탐색 및 클릭 시도
        start_time = time.time()
        while time.time() - start_time < timeout:
            for b_type, sel in yes_selectors:
                try:
                    btns = driver.find_elements(b_type, sel)
                    for btn in btns:
                        if btn.is_displayed():
                            # 방법 A: JS 클릭 (오버레이 무시 가능)
                            try: driver.execute_script("arguments[0].click();", btn)
                            except: pass
                            
                            # 방법 B: 일반 클릭
                            try: btn.click()
                            except: pass
                            
                            # 방법 C: 엔터키 입력
                            try: btn.send_keys(Keys.ENTER)
                            except: pass
                            
                            print(f"   [팝업] '예' 버튼 클릭 시도 완료 ({sel})")
                            return True
                except: continue
            time.sleep(0.5)
            
    except Exception as e:
        print(f"   [주의] '예' 버튼 처리 중 오류: {e}")
    return False

def get_current_applied_discount(driver):
    """현재 적용된 할인 내역 텍스트를 파싱하여 반환합니다."""
    try:
        # 방법 1: 고유 ID 요소 확인 (예: 6시간 (360분))
        try:
            summary = driver.find_element(By.ID, "mf_wfm_body_invokedTkSpan")
            text = summary.text.strip()
            if text:
                return text
        except: pass
                
        # 방법 2: w2group apply_ticket_item 안의 텍스트 확인 (fallback)
        items = driver.find_elements(By.CSS_SELECTOR, ".apply_ticket_item")
        if items:
            return " ".join([item.text for item in items if item.is_displayed()])
    except Exception as e:
        print(f"   [검증] 적용된 할인 읽기 오류: {e}")
    return ""


def cancel_existing_discount(driver, wait):
    """나이스파크에서 한우리교회 할인권 1건을 취소합니다. (시간 수정 재처리 시 사용)"""
    try:
        print("   [재처리] 기존 할인권 취소 시도...")
        # '적용된 할인권' 섹션 내 '전체 취소' 버튼 탐색
        cancel_selectors = [
            (By.CSS_SELECTOR, "input.apply_ticket_alldel"),
            (By.XPATH, "//input[@value='전체 취소']"),
            (By.XPATH, "//*[contains(text(), '전체 취소')]"),
        ]
        cancelled = False
        for by_type, selector in cancel_selectors:
            btns = driver.find_elements(by_type, selector)
            for btn in btns:
                if btn.is_displayed():
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(1.2)
                    
                    # 1. 네이티브 alert 확인 (브라우저 기본 경고창)
                    try:
                        alert = driver.switch_to.alert
                        alert.accept()
                        time.sleep(0.5)
                    except: pass
                    
                    # 2. 커스텀 DOM 팝업(WebSquare) 확인 및 닫기
                    # "이미 취소...", "성공적으로..." 등 모든 알림의 '확인'/'예' 버튼 처리
                    if click_yes_button(driver):
                        print("   [재처리] 안내 팝업('확인'/'예') 처리 완료")
                    
                    cancelled = True
                    print("   [재처리] 취소 명령 전달 완료 및 중복 방지를 위해 탈출")
                    break
            if cancelled: break
        
        if not cancelled:
            print("   [재처리] 취소 버튼 없음 (기존 할인 없는 상태이거나 이미 초기화됨)")
        return cancelled
    except Exception as e:
        print(f"   [재처리] 취소 중 오류: {e}")
        return False


def get_pending_discounts():
    """서버로부터 처리 대기 중인 할인 항목을 가져옵니다."""
    try:
        response = requests.get(f"{FLASK_SERVER_URL}/api/pending-discounts")
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"[오류] 서버 연결 실패: {e}")
        return None

def mark_as_discounted(log_id, status='success', entry_time=None):
    """서버에 할인 처리 결과를 업데이트합니다."""
    try:
        payload = {'status': status}
        if entry_time:
            payload['entry_time'] = entry_time
            
        response = requests.post(
            f"{FLASK_SERVER_URL}/api/mark-discounted/{log_id}",
            json=payload
        )
        return response.status_code == 200
    except Exception as e:
        print(f"[오류] 결과 전송 실패: {e}")
        return False

def run_bot():
    print("=" * 50)
    print(f"나이스파크 자동 할인 봇 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"서버 주소: {FLASK_SERVER_URL}")
    print("=" * 50)
    # ★ [사전 확인] RUN_ONCE(GitHub Actions) 환경에서는 로그인 전에 처리 대상 먼저 조회
    # → 대기 항목이 없으면 Chrome 드라이버 실행 자체를 생략하여 리소스 절약
    if RUN_ONCE:
        print("[사전 확인] 처리 대기 항목 조회 중...")
        pre_check = get_pending_discounts()
        if not pre_check or pre_check['count'] == 0:
            print("[완료] 처리 대기 항목 없음 → 나이스파크 로그인 생략 후 종료합니다.")
            return
        print(f"[확인] {pre_check['count']}건 처리 대기 중 → 나이스파크 접속 및 로그인 진행.")

    # 크롬 드라이버 설정
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")

    # 차단 회피를 위한 User-Agent 설정
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")

    # Railway 환경 감지: RAILWAY_SERVICE_NAME 또는 RAILWAY_ENVIRONMENT 환경 변수로 판단
    import shutil
    IS_RAILWAY = bool(os.environ.get("RAILWAY_SERVICE_NAME") or os.environ.get("RAILWAY_ENVIRONMENT"))
    if IS_RAILWAY:
        # nixpkgs로 설치된 chromium + chromedriver를 함께 사용 (버전 일치 보장)
        chromium_bin = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
        chromedriver_bin = shutil.which("chromedriver")
        if chromium_bin:
            chrome_options.binary_location = chromium_bin
            print(f"[환경] Railway 감지 → chromium: {chromium_bin}")
        else:
            print("[경고] Railway 환경이나 chromium 바이너리를 찾을 수 없습니다.")
        if chromedriver_bin:
            print(f"[환경] Railway 감지 → chromedriver: {chromedriver_bin}")
            driver = webdriver.Chrome(service=Service(chromedriver_bin), options=chrome_options)
        else:
            print("[경고] chromedriver를 찾을 수 없습니다. selenium-manager로 폴백합니다.")
            driver = webdriver.Chrome(options=chrome_options)
    else:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 20) # 대기 시간 20초로 연장

    try:
        # 1. 나이스파크 접속
        print("[안내] 나이스파크 웹할인 시스템 접속 중 (Action 버전)...")
        driver.get("https://npdc-i.nicepark.co.kr/") 
        
        # 2. 자동 로그인 시도
        if not NICEPARK_ID or not NICEPARK_PW:
            print("[에러] NICEPARK_ID 또는 NICEPARK_PW 환경 변수가 설정되지 않았습니다.")
            return

        print(f"[진행] 자동 로그인 시도 중... (ID: {NICEPARK_ID[:3]}***)")
        try:
            # 1. 아이디 입력 (JS 주입 + 이벤트 트리거로 프레임워크 인식 유도)
            print("   -> 아이디 필드 입력 및 이벤트 발생 중...")
            user_field = wait.until(EC.visibility_of_element_located((By.ID, "mf_wfm_body_ibx_empCd")))
            driver.execute_script("""
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
            """, user_field, NICEPARK_ID)
            print("   -> 아이디 동기화 완료")
            
            # 2. 비밀번호 입력 (JS 주입 + 더 강력한 이벤트 트리거)
            print("   -> 비밀번호 필드 입력 및 강제 동기화 중...")
            pw_field = driver.find_element(By.ID, "mf_wfm_body_sct_password")
            driver.execute_script("""
                arguments[0].focus();
                arguments[0].value = arguments[1];
                arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
            """, pw_field, NICEPARK_PW)
            # 확실함을 위해 마지막에 Tab 키 전송 (포커스 이동 유도)
            pw_field.send_keys(Keys.TAB)
            print("   -> 비밀번호 동기화 완료")
            
            # 3. 로그인 버튼 클릭
            print("   -> 로그인 버튼 클릭 중...")
            login_btn = driver.find_element(By.ID, "mf_wfm_body_btn_login")
            driver.execute_script("arguments[0].click();", login_btn)
            
            # 4. 로그인 결과 대기 (조회 버튼 등장 확인)
            print("   -> 로그인 처리 대기 중 (최대 20초)...")
            wait.until(EC.presence_of_element_located((By.ID, "mf_wfm_body_wq_uuid_162")))
            print("[확인] 자동 로그인 성공 및 할인 페이지 진입!")
            
        except Exception as e:
            print(f"[에러] 단계별 진행 중 오류 발생: {e}")
            # 진단용 스크린샷 저장
            driver.save_screenshot("login_error.png")
            print("[조치] 진단용 스크린샷(login_error.png) 저장 완료")
            # 입력 상태 디버깅용 로그
            try:
                val_id = driver.find_element(By.ID, "mf_wfm_body_ibx_empCd").get_attribute("value")
                val_pw = driver.find_element(By.ID, "mf_wfm_body_sct_password").get_attribute("value")
                print(f"   [상태] ID 필드: {'채워짐' if val_id else '비어있음'}, PW 필드: {'채워짐' if val_pw else '비어있음'}")
            except: pass
            return
        
        while True:
            # 2. 처리 대기 목록 가져오기
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 서버 대기 항목 확인 중...")
            data = get_pending_discounts()
            
            if data and data['count'] > 0:
                print(f"-> 처리 대기 항목 {data['count']}건 발견!")
                
                for item in data['items']:
                    log_id = item['id']
                    car_number = item['car_number']
                    stay_hours = item['stay_hours']
                    is_retry = item.get('is_retry', False)  # 시간 수정 후 재처리 여부
                    
                    retry_label = "[재처리]" if is_retry else "[최초]"
                    print(f"")
                    print(f"{'='*44}")
                    print(f"   ▶ {retry_label} {car_number} ({stay_hours}) 처리 시작")
                    print(f"{'='*44}")

                    # 처리 시작 전 '할인적용' 메뉴 클릭으로 화면 초기화 후 페이지 로드 대기
                    reset_to_discount_page(driver)
                    try:
                        wait.until(EC.element_to_be_clickable((By.ID, "mf_wfm_body_wq_uuid_162")))
                        print(f"   [준비] 할인적용 페이지 로드 완료 → 키패드 입력 시작")
                    except:
                        print(f"   [주의] 조회 버튼 대기 시간 초과, 계속 진행")

                    try:
                        # 4자리 추출 (검색용)
                        last_4 = car_number.replace(" ", "")[-4:]

                        # [1단계] 가상 키패드 입력
                        print(f"   [1단계] 가상 키패드 입력: '{last_4}' (차량번호: {car_number})")
                        for digit in last_4:
                            digit_int = int(digit)
                            uuid_prefix = "mf_wfm_body_wq_uuid_"
                            uuid_suffix = 140 + (digit_int - 1) * 2 if digit_int != 0 else 158

                            try:
                                btn = wait.until(EC.element_to_be_clickable((By.ID, f"{uuid_prefix}{uuid_suffix}")))
                                btn.click()
                                time.sleep(0.3)
                            except Exception as e:
                                print(f"      - [경고] UUID 클릭 실패(digit={digit}), 폴백 시도 중...")
                                try:
                                    fallback_btn = driver.find_element(
                                        By.XPATH,
                                        f"//input[contains(@class,'carNumBtn') and @value='{digit}']"
                                    )
                                    fallback_btn.click()
                                    print(f"      - [폴백 성공] input[@value='{digit}'] 클릭")
                                except Exception as e2:
                                    print(f"      - [오류] '{digit}' 입력 최종 실패: {e2}")

                        # [2단계] 조회 버튼 클릭
                        print(f"   [2단계] '{last_4}' 입력완료 → 조회 버튼 클릭")
                        wait.until(EC.element_to_be_clickable((By.ID, "mf_wfm_body_wq_uuid_162"))).click()
                        time.sleep(1.5)


                        # --- 알림창 감지 (DOM 기반: title="알림" 헤더 탐지) ---
                        alert_type = None # None, 'not_found', 'already_done'
                        try:
                            # 1. "알림" 팝업 헤더 DOM 탐지
                            alert_visible = driver.execute_script("""
                                var headers = document.querySelectorAll("div[id*='alert'][id$='_header']");
                                for (var h of headers) {
                                    if (h.title === '알림' && h.offsetParent !== null) return true;
                                }
                                return false;
                            """)

                            if alert_visible:
                                # 2. 팝업 종류 판별 (textarea 텍스트 검색 불가 → DOM 상태로 구분)
                                # - 차량번호 표시(mf_wfm_body_carNoText)가 비어있으면 → 차량 없음
                                # - 차량번호 + 적용시간(mf_wfm_body_invokedTkSpan) 둘 다 있으면 → 이미 할인됨
                                car_no_text = driver.execute_script("""
                                    var el = document.getElementById('mf_wfm_body_carNoText');
                                    return el ? el.textContent.trim() : '';
                                """)
                                invoked_text = driver.execute_script("""
                                    var el = document.getElementById('mf_wfm_body_invokedTkSpan');
                                    return el ? el.textContent.trim() : '';
                                """)
                                print(f"   [팝업 분석] carNoText='{car_no_text}' / invokedTkSpan='{invoked_text}'")

                                if car_no_text == '':
                                    print(f"   [알림] 알림창 감지 + 차량번호 없음 → '검색된 차량이 없습니다' 간주 ({car_number})")
                                    alert_type = 'not_found'
                                elif car_no_text and invoked_text:
                                    print(f"   [알림] 알림창 감지 + 차량번호/시간 있음 → '최대 사용매수 초과' 간주 ({car_number})")
                                    alert_type = 'already_done'
                                else:
                                    print(f"   [알림] 알림창 감지됐으나 유형 불명 → ESC로 닫고 계속 진행")
                                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                                    time.sleep(0.5)

                            # 3. 알림창 닫기 (ESC 키 우선)
                            if alert_type == 'not_found':
                                print(f"   [조치] 알림창 닫기 → ESC 키 입력")
                                try:
                                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                                    time.sleep(0.8)
                                    print(f"   [조치] ESC 키 입력 완료 → 팝업 닫힘")
                                except Exception as e:
                                    print(f"   [주의] ESC 키 실패: {e}")

                                mark_as_discounted(log_id, status='not_found')
                                reset_to_discount_page(driver)
                                continue

                            elif alert_type == 'already_done':
                                # already_done: ESC로 닫고 입차시간 수집 계속
                                print(f"   [조치] 알림창 닫기 → ESC 키 입력")
                                try:
                                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                                    time.sleep(0.5)
                                except: pass
                                print("      - [알림] 이미 할인된 차량입니다. 입차 정보 수집을 위해 계속 진행합니다.")
                        except: pass

                        # --- 상세 매칭 및 입차시간 수집 ---
                        entry_time = None
                        matched = False
                        
                        try:
                            # 1. [팝업] '차량번호 선택' 팝업이 뜬 경우를 최우선으로 확인
                            if not matched:
                                try:
                                    popup_titles = driver.find_elements(By.XPATH, "//*[contains(text(), '차량번호 선택') or contains(@class, 'w2dialog_title')]")
                                    if any(p.is_displayed() for p in popup_titles):
                                        print(f"   [매칭] '차량번호 선택' 팝업 감지 (전체 페이지 탐색 중...)")
                                        
                                        pages_checked = 0
                                        car_number_clean = car_number.replace(" ", "")
                                        while not matched and pages_checked < 5: # 최대 5페이지까지 탐색
                                            pages_checked += 1
                                            # col_id="carNo" td 중 현재 화면에 보이는 것만 처리
                                            # (페이지 이동 후에도 이전 페이지 DOM이 남아 있으므로 is_displayed() 필터 필수)
                                            car_no_tds = driver.find_elements(By.XPATH, "//td[@col_id='carNo']")
                                            for car_td in car_no_tds:
                                                # 화면에 보이지 않는 요소(이전 페이지 잔존 DOM) 제외
                                                try:
                                                    if not car_td.is_displayed():
                                                        continue
                                                except:
                                                    continue

                                                try:
                                                    popup_car = car_td.find_element(By.TAG_NAME, "nobr").text.replace(" ", "")
                                                except:
                                                    popup_car = car_td.text.replace(" ", "")

                                                print(f"   [팝업 확인] 화면 차량번호: '{popup_car}' / 등록: '{car_number_clean}'")

                                                if not popup_car:
                                                    continue
                                                # 공백 제거 후 전체 번호 완전 일치만 허용 (부분 포함 불가)
                                                if popup_car != car_number_clean:
                                                    print(f"   [팝업 스킵] '{popup_car}' 은 '{car_number_clean}' 과 다름")
                                                    continue

                                                # td ID에서 행 인덱스 추출 → 같은 행의 버튼 td를 ID로 정확히 특정
                                                # ID 형식: mf_wfm_body_list_carGridView_cell_{rowIdx}_{colIdx}
                                                td_id = car_td.get_attribute("id") or ""
                                                btn_td_id = td_id.replace("_1_", "_3_") if "_1_" in td_id else ""

                                                # 입차시간 추출
                                                p_row = car_td.find_element(By.XPATH, "./ancestor::tr[1]")
                                                extracted = extract_hhmm(p_row.text)
                                                if extracted:
                                                    entry_time = extracted
                                                    print(f"   [정보] 입차시간 추출: {entry_time}")

                                                print(f"   [매칭] 팝업 {pages_checked}페이지에서 '{popup_car}' 정확 일치 → 선택 (td id: {btn_td_id or 'fallback'})")
                                                try:
                                                    if alert_type == 'already_done':
                                                        print("      - [진행] 이미 할인된 차량이므로 '선택' 클릭은 생략하고 정보만 수집합니다.")
                                                    else:
                                                        # 1순위: ID로 버튼 td를 정확히 찾아 클릭
                                                        clicked = False
                                                        if btn_td_id:
                                                            try:
                                                                btn = driver.find_element(By.ID, btn_td_id).find_element(By.TAG_NAME, "button")
                                                                driver.execute_script("arguments[0].click();", btn)
                                                                clicked = True
                                                            except:
                                                                pass
                                                        # 2순위: 같은 tr 안의 col_id="carBtn" 버튼
                                                        if not clicked:
                                                            btn = p_row.find_element(By.XPATH, ".//td[@col_id='carBtn']//button")
                                                            driver.execute_script("arguments[0].click();", btn)
                                                except Exception as btn_err:
                                                    if alert_type != 'already_done':
                                                        print(f"   [주의] 선택 버튼 클릭 실패: {btn_err}")

                                                matched = True
                                                if alert_type != 'already_done':
                                                    time.sleep(2.0) # 팝업 닫힘 대기
                                                break

                                            if matched: break
                                            
                                            # 다음 페이지 버튼 확인 및 클릭
                                            try:
                                                next_btn = None
                                                try:
                                                    next_btn = driver.find_element(By.ID, "mf_wfm_body_btnNextCar")
                                                except:
                                                    next_btn = driver.find_element(By.XPATH, "//input[@value='다음페이지']")
                                                
                                                if next_btn and next_btn.is_displayed():
                                                    print(f"   [진행] {pages_checked}페이지에 없음 -> 다음 페이지 이동 중...")
                                                    driver.execute_script("arguments[0].click();", next_btn)
                                                    time.sleep(1.5) # 페이지 로딩 대기
                                                else: break
                                            except: break
                                        
                                        # 끝까지 못 찾은 경우 [닫기] 버튼 클릭 (강력한 탐색 모드)
                                        if not matched:
                                            print(f"   [실패] 모든 페이지 탐색했으나 {car_number} 없음. 팝업을 닫습니다 (강력 모드).")
                                            try:
                                                close_btn = None
                                                try: close_btn = driver.find_element(By.ID, "mf_wfm_body_wq_uuid_250")
                                                except: pass
                                                
                                                if not close_btn:
                                                    try: close_btn = driver.find_element(By.XPATH, "//input[@value='닫기']")
                                                    except: close_btn = driver.find_element(By.XPATH, "//*[text()='닫기' or contains(text(), '닫기')]")
                                               
                                                if close_btn: driver.execute_script("arguments[0].click();", close_btn)
                                                
                                                x_btns = driver.find_elements(By.XPATH, "//*[contains(@class, 'close') and contains(@class, 'window')] | //a[contains(@class, 'w2window_close')]")
                                                for x in x_btns:
                                                    if x.is_displayed(): driver.execute_script("arguments[0].click();", x)
                                                
                                                time.sleep(1.5)
                                            except Exception as close_err:
                                                print(f"   [주의] 팝업 닫기 버튼 작동 실패: {close_err}")

                                except Exception as e:
                                    print(f"   [주의] 팝업 처리 중 건너뜀: {e}")
                            # 2. [목록] 검색 결과 목록(Table)에서 선택
                            if not matched:
                                rows = driver.find_elements(By.CSS_SELECTOR, "tr[id*='gen_searchList']")
                                for row in rows:
                                    row_text_clean = row.text.replace(" ", "")
                                    if car_number.replace(" ", "") in row_text_clean:
                                        print(f"   [매칭] 목록 테이블에서 '{car_number}' 항목 선택")
                                        
                                        tds = row.find_elements(By.TAG_NAME, "td")
                                        for td in tds:
                                            extracted = extract_hhmm(td.text.strip())
                                            if extracted:
                                                entry_time = extracted
                                                print(f"   [정보] 입차시간 추출: {entry_time}")
                                                break
                                        
                                        if alert_type != 'already_done':
                                            row.click()
                                        matched = True
                                        time.sleep(1.0)
                                        break

                            # 3. [즉시] 검색 결과가 단 하나여서 정보가 바로 노출된 경우
                            if not matched:
                                try:
                                    detail_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '입차시간')]")
                                    if any(d.is_displayed() for d in detail_elements):
                                        car_number_clean = car_number.replace(" ", "")
                                        car_verified = False

                                        # 방법1: 나이스파크 차량번호 td (data-title 속성)
                                        try:
                                            car_td = driver.find_element(By.XPATH, "//td[@data-title='차량번호']")
                                            shown_car = car_td.text.replace(" ", "")
                                            print(f"   [검증] 화면 차량번호: '{shown_car}' / 등록: '{car_number_clean}'")
                                            if shown_car and (car_number_clean in shown_car or shown_car in car_number_clean):
                                                car_verified = True
                                        except: pass

                                        # 방법2: 입력창(mf_wfm_body_carNoText) 값 확인
                                        if not car_verified:
                                            try:
                                                car_inp = driver.find_element(By.ID, "mf_wfm_body_carNoText")
                                                input_val = car_inp.get_attribute("value").replace(" ", "")
                                                print(f"   [검증] 입력창 값: '{input_val}' / 등록: '{car_number_clean}'")
                                                if input_val and (car_number_clean in input_val or input_val in car_number_clean):
                                                    car_verified = True
                                            except: pass

                                        # 방법3: 뒤 4자리 폴백은 제거 — 다른 차량과 오탐 발생 위험 높음
                                        # (예: 등록 '111가2222' vs 나이스파크 '01더2222' → 4자리 '2222' 일치로 오매칭)

                                        if car_verified:
                                            print(f"   [매칭] 단일 결과 즉시 매칭 성공")
                                            matched = True
                                            # 입차시간 추출 (여러 XPath 시도)
                                            for xpath in [
                                                "//*[contains(text(),'입차시간')]/following-sibling::*[1]",
                                                "//td[@data-title='입차시간']",
                                                "//*[(self::label or self::span) and contains(text(),'입차시간')]/following-sibling::*[1]",
                                            ]:
                                                try:
                                                    for el in driver.find_elements(By.XPATH, xpath):
                                                        extracted = extract_hhmm(el.text.strip())
                                                        if extracted:
                                                            entry_time = extracted
                                                            print(f"   [정보] 입차시간 추출: {entry_time}")
                                                            break
                                                    if entry_time: break
                                                except: pass
                                        else:
                                            print(f"   [실패] 화면 차량번호 '{car_number}'과 불일치")
                                except Exception as e3:
                                    print(f"   [주의] 즉시 매칭 처리 중 오류: {e3}")

                            if not matched:
                                print(f"   [실패] 전체 번호 {car_number} 매칭 실패 (차량 선택 불가)")
                                mark_as_discounted(log_id, status='not_found')
                                reset_to_discount_page(driver)
                                continue
                        except Exception as e:
                            print(f"   [오류] 상세 매칭 분석 중 에러: {e}")
                            mark_as_discounted(log_id, status='not_found')
                            continue

                        # --- 모달 팝업 닫기 (할인 버튼 가리는 경우 대비) ---
                        try:
                            modal = driver.find_element(By.ID, "_modal")
                            if modal.is_displayed():
                                print("   [조치] _modal 팝업 감지 → JS로 강제 숨김 처리")
                                driver.execute_script("document.getElementById('_modal').style.display='none';")
                        except: pass

                        # --- 차량번호 최종 검증 (할인 적용 전 필수 확인) ---
                        # 팝업에서 잘못된 차량이 선택된 경우를 방지하기 위해
                        # 화면에 표시된 전체 차량번호가 등록 차량번호와 일치하는지 반드시 확인
                        if alert_type != 'already_done':
                            time.sleep(0.8)
                            confirmed_car = None
                            car_number_clean = car_number.replace(" ", "")
                            try:
                                car_td = driver.find_element(By.XPATH, "//td[@data-title='차량번호']")
                                confirmed_car = car_td.text.replace(" ", "")
                            except: pass
                            if not confirmed_car:
                                try:
                                    car_inp = driver.find_element(By.ID, "mf_wfm_body_carNoText")
                                    confirmed_car = car_inp.get_attribute("value").replace(" ", "")
                                except: pass

                            if confirmed_car:
                                # 공백 제거 후 전체 번호 완전 일치만 허용 (부분 포함 불가)
                                if confirmed_car == car_number_clean:
                                    print(f"   [검증 통과] 화면 차량번호 '{confirmed_car}' ↔ 등록 '{car_number_clean}' 일치 → 할인 적용 진행")
                                else:
                                    print(f"   [검증 실패] 화면 차량번호 '{confirmed_car}' ↔ 등록 '{car_number_clean}' 불일치 → 할인 적용 중단")
                                    mark_as_discounted(log_id, status='not_found')
                                    reset_to_discount_page(driver)
                                    continue
                            else:
                                print(f"   [경고] 선택 후 화면에서 차량번호를 읽을 수 없음 → 안전을 위해 할인 적용 중단")
                                mark_as_discounted(log_id, status='not_found')
                                reset_to_discount_page(driver)
                                continue

                        # --- 이미 할인된 경우(already_done) 최종 처리 ---
                        if alert_type == 'already_done':
                            print(f"   [성공] 이미 할인된 차량 확인 완료. 입차시간: {entry_time}")
                            mark_as_discounted(log_id, status='success', entry_time=entry_time)
                            reset_to_discount_page(driver)
                            continue # 다음 차량으로

                        # --- 사전 검증 (Pre-check) ---
                        time.sleep(1.0)
                        applied_text = get_current_applied_discount(driver)
                        target_hours = stay_hours.split('(')[0].replace(' ', '') # "6시간"
                        
                        # 9시간(종일) 예외 처리
                        display_target = "24시간" if "9시간" in target_hours else target_hours
                        
                        if display_target in applied_text.replace(' ', ''):
                            print(f"   [검증] 등록하려는 시간({target_hours})과 현재 적용된 할인({applied_text.strip()})이 같으므로 스킵합니다.")
                            if mark_as_discounted(log_id, entry_time=entry_time):
                                print(f"   [성공] 할인 스킵(기적용 확인)! 입차시간: {entry_time}")
                            else:
                                print("   [주의] 서버 업데이트 실패")
                            continue
                        elif applied_text.strip():
                            print(f"   [검증] 기존 할인({applied_text.strip()})과 다르므로 기존 할인을 '전체 취소'하고 재적용합니다.")
                            cancel_existing_discount(driver, wait)
                            time.sleep(1.0)
                        elif is_retry:
                            print(f"   [재처리] 텍스트 확인 불가하나 재처리 플래그 감지 - 예방적 '전체 취소' 시도")
                            cancel_existing_discount(driver, wait)
                            time.sleep(1.0)

                        # --- 할인권 적용 ---
                        # 할인 시간 → 할인권 인덱스 매핑
                        tk_idx = "1"  # 기본 3시간
                        if "24시간" in stay_hours: tk_idx = "3"
                        elif "9시간" in stay_hours: tk_idx = "3"  # 9시간(종일) → 24시간 버튼
                        elif "6시간" in stay_hours: tk_idx = "2"
                        elif "2시간" in stay_hours: tk_idx = "0"

                        discount_btn_id = f"mf_wfm_body_gen_dcTkList_{tk_idx}_discountTkGrp"
                        print(f"   [진행] 할인 버튼 클릭: {discount_btn_id} ({stay_hours})")

                        try:
                            discount_btn = wait.until(EC.presence_of_element_located((By.ID, discount_btn_id)))
                            
                            verified = False
                            for attempt in range(2): # 기본 1회 + 재시도 1회 = 총 2회
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", discount_btn)
                                time.sleep(0.3)
                                driver.execute_script("arguments[0].click();", discount_btn)
                                time.sleep(1.5)
                                
                                try:
                                    alert = driver.switch_to.alert
                                    alert.accept()
                                except:
                                    # 커스텀 DOM 모달 대응 ("예" 버튼 클릭)
                                    if click_yes_button(driver):
                                        print("   [진행] 할인 적용 확인 팝업 처리 완료")
                                
                                # --- 사후 검증 (Post-check) ---
                                time.sleep(1.5)
                                post_applied_text = get_current_applied_discount(driver)
                                if display_target in post_applied_text.replace(' ', ''):
                                    verified = True
                                    break
                                else:
                                    if attempt == 0:
                                        print(f"   [검증] 적용내역 확인불가 (현재: {post_applied_text.strip()}). 1회 재시도합니다.")
                                        cancel_existing_discount(driver, wait) # 초기화 후 루프 재시작
                                        time.sleep(1.0)
                                    else:
                                        print(f"   [실패] 재시도 이후에도 윈하는 할인({target_hours}) 적용이 확인되지 않습니다.")
                            
                            if verified:
                                if mark_as_discounted(log_id, entry_time=entry_time):
                                    print(f"   [성공] 할인 최종 확정! 입차시간: {entry_time}")
                                else:
                                    print("   [주의] 서버 업데이트 실패")
                            else:
                                mark_as_discounted(log_id, status='failed', entry_time=entry_time)

                        except Exception as e:
                            print(f"   [실패] 할인 동작 오류: {e}")
                            mark_as_discounted(log_id, status='not_found')
                            reset_to_discount_page(driver)

                    except Exception as e:
                        print(f"   [오류] {car_number} 처리 중 중단: {e}")
                        reset_to_discount_page(driver)
                
            else:
                print("   [안내] 대기 항목 없음")
            
            if RUN_ONCE: break
            time.sleep(10)

    except KeyboardInterrupt:
        print("\n[중단] 봇 종료")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_bot()
