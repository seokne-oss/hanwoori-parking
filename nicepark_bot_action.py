import time
import os
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
FLASK_SERVER_URL = os.environ.get("FLASK_SERVER_URL", "https://hanwoori-parking.up.railway.app")
RUN_ONCE = os.environ.get("RUN_ONCE", "true").lower() == "true"
NICEPARK_ID = os.environ.get("NICEPARK_ID")
NICEPARK_PW = os.environ.get("NICEPARK_PW")
# GitHub Action 버전은 항상 헤드리스로 실행되며 자동 로그인을 시도합니다.

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
            (By.XPATH, "//input[contains(@class, 'btn_cm') and contains(@value, '예')]"),
            (By.XPATH, "//*[contains(@class, 'w2window')]//input[contains(@value, '예')]"),
            (By.CSS_SELECTOR, "input[id*='_btn_yes']"),
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
                    time.sleep(1.0)
                    # 팝업 확인 처리 (네이티브 alert 또는 DOM 모달)
                    try:
                        alert = driver.switch_to.alert
                        alert.accept()
                        time.sleep(0.5)
                    except:
                        # 커스텀 DOM 모달 대응 ("예" 버튼 클릭)
                        if click_yes_button(driver):
                            print("   [재처리] 팝업 '예' 버튼 처리 성공")
                        
                        print("   [재처리] 기존 할인권 전체 취소 명령 전달 완료")
                        cancelled = True
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

    # 크롬 드라이버 설정
    chrome_options = Options()
    # GitHub Action 버전은 화면 없이 실행합니다.
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")

    # 차단 회피를 위한 User-Agent 설정
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")
    
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
                    print(f"   [진행] {retry_label} {car_number} ({stay_hours}) 처리 중...")
                    
                    try:
                        # 4자리 추출 (검색용)
                        last_4 = car_number.replace(" ", "")[-4:]
                        
                        # 번호 입력 (가상 키패드 대응)
                        for digit in last_4:
                            digit_str = str(digit)
                            print(f"      - 숫자 {digit_str} 입력 중...")
                            success = False
                            
                            # 1. 태그에 상관없이 숫자를 텍스트로 가진 요소 탐색 (가장 확실함)
                            try:
                                # 웹스퀘어 가상 키패드 내부에서 해당하는 숫자 텍스트를 가진 요소 클릭
                                digit_btn = driver.find_element(By.XPATH, f"//div[@id='mf_wfm_body']//*[text()='{digit_str}']")
                                if digit_btn.is_displayed():
                                    driver.execute_script("arguments[0].click();", digit_btn)
                                    success = True
                                    print(f"      - 숫자 {digit_str} 입력 성공")
                            except: pass
                            
                            # 2. 보조용 ID 기반 (실패 시 대비)
                            if not success:
                                try:
                                    digit_int = int(digit)
                                    uuid_suffix = 140 + (digit_int - 1) * 2 if digit_int != 0 else 158
                                    btn = driver.find_element(By.ID, f"mf_wfm_body_wq_uuid_{uuid_suffix}")
                                    driver.execute_script("arguments[0].click();", btn)
                                    success = True
                                except: pass
                            
                            time.sleep(0.4)
                        
                        # 조회 버튼 클릭 (JS 방식으로 가로막힘 방지)
                        print("      - 조회 버튼 클릭 중...")
                        search_btn = wait.until(EC.presence_of_element_located((By.ID, "mf_wfm_body_wq_uuid_162")))
                        driver.execute_script("arguments[0].click();", search_btn)
                        time.sleep(1.5)


                        # --- 알림창 감지 (중복 할인, 차량 없음 등) ---
                        alert_type = None # None, 'not_found', 'already_done'
                        try:
                            # 1. 텍스트 감지
                            page_text = driver.page_source
                            if "검색된 차량이 없습니다" in page_text:
                                print(f"   [알림] 검색 결과가 없습니다. ({car_number})")
                                alert_type = 'not_found'
                            elif "최대 사용매수" in page_text or "이미 사용" in page_text:
                                print(f"   [알림] 이미 할인이 적용된 차량입니다. ({car_number})")
                                alert_type = 'already_done'
                            
                            # 2. 알림창 닫기 및 상태 보고
                            if alert_type:
                                selectors = [
                                    (By.CSS_SELECTOR, "input[id$='_btn_conf']"), 
                                    (By.XPATH, "//input[@value='확인']"),
                                    (By.XPATH, "//*[contains(text(), '확인')]")
                                ]
                                for by_type, selector in selectors:
                                    btns = driver.find_elements(by_type, selector)
                                    for btn in btns:
                                        if btn.is_displayed():
                                            driver.execute_script("arguments[0].click();", btn)
                                            print(f"   [조치] 알림창({alert_type}) 닫기 완료")
                                            time.sleep(0.5)
                                            break
                                    if alert_type: break
                                
                                # 상태에 따른 서버 보고
                                time.sleep(1.0)
                                clear_input_field(driver)
                                
                                if alert_type == 'not_found':
                                    mark_as_discounted(log_id, status='not_found')
                                else:
                                    mark_as_discounted(log_id, status='success', entry_time='이미 적용됨')
                                continue
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
                                        while not matched and pages_checked < 5: # 최대 5페이지까지 탐색
                                            pages_checked += 1
                                            # 팝업 내 모든 행(tr)을 탐색
                                            popup_rows = driver.find_elements(By.XPATH, "//tr[contains(., '선택')]")
                                            for p_row in popup_rows:
                                                p_text = p_row.text.replace(" ", "")
                                                if car_number.replace(" ", "") in p_text:
                                                    print(f"   [매칭] 팝업 {pages_checked}페이지에서 '{car_number}' 일치 항목 선택")
                                                    
                                                    # 입차시간 추출
                                                    if ":" in p_row.text:
                                                        time_parts = [t for t in p_row.text.split() if ":" in t]
                                                        if time_parts:
                                                            entry_time = time_parts[-1]

                                                    # 실제 <button> 태그 정밀 타겟팅 (사용자 제공 정보 반영)
                                                    try:
                                                        # 행 내부의 모든 button 중 '선택' 텍스트를 가진 요소 탐색
                                                        action_btns = p_row.find_elements(By.XPATH, ".//button[text()='선택' or contains(text(), '선택')]")
                                                        if not action_btns:
                                                            # 폴백: td 내부의 버튼 구조
                                                            action_btns = p_row.find_elements(By.XPATH, ".//td[contains(@value, '선택')]//button")
                                                        
                                                        if action_btns:
                                                            driver.execute_script("arguments[0].click();", action_btns[0])
                                                        else:
                                                            # 최후의 수단: 텍스트 기반 클릭
                                                            fallback_btn = p_row.find_element(By.XPATH, ".//*[contains(text(), '선택')]")
                                                            driver.execute_script("arguments[0].click();", fallback_btn)
                                                    except Exception as btn_err:
                                                        print(f"   [주의] 선택 버튼 클릭 실패: {btn_err}")

                                                    matched = True
                                                    time.sleep(2.0) # 팝업 닫힘 대기
                                                    break
                                            
                                            if matched: break
                                            
                                            # 다음 페이지 버튼 확인 및 클릭
                                            try:
                                                # 사용자 제공 ID 및 Value 적용
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
                                                # 공식 구조 반영: value='닫기'인 input 및 조상 탐색
                                                close_btn = None
                                                try:
                                                    close_btn = driver.find_element(By.ID, "mf_wfm_body_wq_uuid_250") # ID는 변할 수 있음
                                                except: pass
                                                
                                                if not close_btn:
                                                    try:
                                                        close_btn = driver.find_element(By.XPATH, "//input[@value='닫기']")
                                                    except:
                                                        close_btn = driver.find_element(By.XPATH, "//*[text()='닫기' or contains(text(), '닫기')]")
                                               
                                                if close_btn:
                                                    driver.execute_script("arguments[0].click();", close_btn)
                                                
                                                # 백업: X 버튼 탐색
                                                x_btns = driver.find_elements(By.XPATH, "//*[contains(@class, 'close') and contains(@class, 'window')] | //a[contains(@class, 'w2window_close')]")
                                                for x in x_btns:
                                                    if x.is_displayed():
                                                        driver.execute_script("arguments[0].click();", x)
                                                
                                                time.sleep(1.5) # 닫힘 대기
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
                                            t = td.text.strip()
                                            if ":" in t and (len(t) == 5 or len(t) >= 16):
                                                entry_time = t.split()[-1]
                                                break
                                        
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
                                            if car_number_clean in shown_car or shown_car in car_number_clean:
                                                car_verified = True
                                        except: pass

                                        # 방법2: 입력창(mf_wfm_body_carNoText) 값 확인
                                        if not car_verified:
                                            try:
                                                car_inp = driver.find_element(By.ID, "mf_wfm_body_carNoText")
                                                input_val = car_inp.get_attribute("value").replace(" ", "")
                                                print(f"   [검증] 입력창 값: '{input_val}' / 등록: '{car_number_clean}'")
                                                if input_val and (car_number_clean[-4:] in input_val or input_val[-4:] in car_number_clean):
                                                    car_verified = True
                                            except: pass

                                        # 방법3: page_source 뒤 4자리 폴백
                                        if not car_verified:
                                            try:
                                                if car_number_clean[-4:] in driver.page_source.replace(" ", ""):
                                                    print(f"   [검증] 페이지에서 뒤 4자리({car_number_clean[-4:]}) 확인 → 매칭 허용")
                                                    car_verified = True
                                            except: pass

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
                                                        t = el.text.strip()
                                                        if ':' in t and len(t) >= 5:
                                                            entry_time = t.split()[-1]
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
                                clear_input_field(driver)
                                mark_as_discounted(log_id, status='not_found')
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
                                time.sleep(0.5)
                        except: pass

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
                            clear_input_field(driver)
                            mark_as_discounted(log_id, status='not_found')

                    except Exception as e:
                        print(f"   [오류] {car_number} 처리 중 중단: {e}")
                        clear_input_field(driver)
                
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
