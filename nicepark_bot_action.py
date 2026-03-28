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
from webdriver_manager.chrome import ChromeDriverManager

# --- 설정 및 환경 변수 ---
FLASK_SERVER_URL = os.environ.get("FLASK_SERVER_URL", "http://127.0.0.1:5000")
RUN_ONCE = os.environ.get("RUN_ONCE", "true").lower() == "true"
NICEPARK_ID = os.environ.get("NICEPARK_ID")
NICEPARK_PW = os.environ.get("NICEPARK_PW")
# GitHub Action 버전은 항상 헤드리스로 실행되며 자동 로그인을 시도합니다.

def clear_input_field(driver):
    """차량번호 입력 필드를 백스페이스 4번으로 초기화합니다."""
    try:
        actions = webdriver.ActionChains(driver)
        for _ in range(4):
            actions.send_keys(Keys.BACKSPACE)
        actions.perform()
        print("   [조치] 입력 필드 초기화 완료 (Backspace 4회)")
    except Exception as e:
        print(f"   [오류] 입력 필드 초기화 실패: {e}")

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

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)

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
            wait.until(EC.presence_of_element_located((By.ID, "user_id"))).send_keys(NICEPARK_ID)
            driver.find_element(By.ID, "user_pw").send_keys(NICEPARK_PW)
            driver.find_element(By.ID, "btn_login").click()
            time.sleep(2)
            
            # 로그인 후 메인 페이지 또는 할인 등록 페이지로 이동했는지 확인
            # '조회' 버튼이 있는지 확인하여 로그인 성공 여부 판단
            wait.until(EC.presence_of_element_located((By.ID, "mf_wfm_body_wq_uuid_162")))
            print("[확인] 자동 로그인 성공 및 할인 페이지 진입!")
        except Exception as e:
            print(f"[에러] 자동 로그인 실패 또는 페이지 진입 불가: {e}")
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
                    
                    print(f"   [진행] {car_number} ({stay_hours}) 처리 중...")
                    
                    try:
                        # 4자리 추출 (검색용)
                        last_4 = car_number.replace(" ", "")[-4:]
                        
                        # 번호 입력
                        for digit in last_4:
                            digit_int = int(digit)
                            uuid_prefix = "mf_wfm_body_wq_uuid_"
                            uuid_suffix = 140 + (digit_int - 1) * 2 if digit_int != 0 else 158
                            
                            try:
                                btn = wait.until(EC.element_to_be_clickable((By.ID, f"{uuid_prefix}{uuid_suffix}")))
                                btn.click()
                                time.sleep(0.3)
                            except:
                                driver.find_element(By.XPATH, f"//a[text()='{digit}']").click()
                        
                        # 조회 버튼 클릭
                        wait.until(EC.element_to_be_clickable((By.ID, "mf_wfm_body_wq_uuid_162"))).click()
                        time.sleep(1.5)
                        
                        # --- 알림창 감지 ---
                        alert_found = False
                        try:
                            selectors = [
                                (By.CSS_SELECTOR, "input[id$='_btn_conf']"),
                                (By.CSS_SELECTOR, ".w2trigger.btn_cm.pt")
                            ]
                            for by_type, selector in selectors:
                                btns = driver.find_elements(by_type, selector)
                                for btn in btns:
                                    if btn.is_displayed():
                                        btn.click()
                                        print("   [조치] 알림창 감지 및 닫기 완료")
                                        time.sleep(0.5)
                                        clear_input_field(driver)
                                        alert_found = True
                                        break
                                if alert_found: break
                        except: pass
                        
                        if alert_found:
                            mark_as_discounted(log_id, status='not_found')
                            continue

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
                                    # 상세 정보(입차시간 등)가 실제로 화면에 출력되었는지 확인
                                    detail_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '입차시간')]")
                                    if any(d.is_displayed() for d in detail_elements):
                                        page_text = driver.page_source
                                        if car_number.replace(" ", "") in page_text.replace(" ", ""):
                                            print(f"   [매칭] 단일 결과 즉시 매칭 성공 (상세 정보 확인)")
                                            matched = True
                                            
                                            # 입차시간 추출
                                            time_element = driver.find_element(By.XPATH, "//*[(self::label or self::span) and contains(text(), '입차시간')]/following-sibling::*[1]")
                                            val = time_element.text.strip()
                                            if ":" in val:
                                                entry_time = val.split()[-1]
                                except: pass

                            if not matched:
                                print(f"   [실패] 전체 번호 {car_number} 매칭 실패 (차량 선택 불가)")
                                clear_input_field(driver)
                                mark_as_discounted(log_id, status='not_found')
                                continue
                        except Exception as e:
                            print(f"   [오류] 상세 매칭 분석 중 에러: {e}")
                            mark_as_discounted(log_id, status='not_found')
                            continue

                        # --- 할인권 적용 ---
                        tk_idx = "1" # 기본 3시간
                        if "24시간" in stay_hours: tk_idx = "3"
                        elif "6시간" in stay_hours: tk_idx = "2"
                        elif "2시간" in stay_hours: tk_idx = "0"
                        
                        discount_btn_id = f"mf_wfm_body_gen_dcTkList_{tk_idx}_discountTkGrp"
                        
                        try:
                            wait.until(EC.element_to_be_clickable((By.ID, discount_btn_id))).click()
                            time.sleep(1.0)
                            try:
                                alert = driver.switch_to.alert
                                alert.accept()
                            except: pass
                            
                            if mark_as_discounted(log_id, entry_time=entry_time):
                                print(f"   [성공] 할인 완료! 입차시간: {entry_time}")
                            else:
                                print("   [주의] 서버 업데이트 실패")
                        except Exception as e:
                            print(f"   [실패] 할인 버튼 오류: {e}")
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
