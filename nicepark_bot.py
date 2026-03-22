import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 설정 사항 (환경 변수 우선) ---
# Railway 배포 주소를 기본값으로 하되 환경변수에서 가져옴
FLASK_SERVER_URL = os.getenv("FLASK_SERVER_URL", "https://hanwoori-parking.up.railway.app").rstrip('/')
NICEPARK_URL = "https://npdc-i.nicepark.co.kr"
NICEPARK_ID = os.getenv("NICEPARK_ID")
NICEPARK_PW = os.getenv("NICEPARK_PW")
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() == "true" # GHA에서는 한 번만 실행

def get_pending_discounts():
    try:
        response = requests.get(f"{FLASK_SERVER_URL}/api/pending-discounts")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Flask 서버 연결 실패 ({FLASK_SERVER_URL}): {e}")
    return None

def mark_as_discounted(log_id, status='success'):
    try:
        response = requests.post(f"{FLASK_SERVER_URL}/api/mark-discounted/{log_id}", json={'status': status})
        return response.status_code == 200
    except Exception as e:
        print(f"상태 업데이트 실패 (ID: {log_id}): {e}")
    return False

def login_nicepark(driver, wait):
    driver.get(NICEPARK_URL)
    
    if NICEPARK_ID and NICEPARK_PW:
        print("환경 변수 정보를 사용하여 자동 로그인을 시도합니다...")
        try:
            # 실 사이트 분석 결과에 따른 ID (WebSquare)
            wait.until(EC.presence_of_element_located((By.ID, "mf_wfm_layout_login_userid"))).send_keys(NICEPARK_ID)
            driver.find_element(By.ID, "mf_wfm_layout_login_password").send_keys(NICEPARK_PW)
            driver.find_element(By.ID, "mf_wfm_layout_login_btnLogin").click()
            
            # 로그인 성공 여부 확인 (메인 페이지의 특정 요소 대기)
            wait.until(lambda d: "login" not in d.current_url.lower())
            print("자동 로그인 성공!")
            return True
        except Exception as e:
            print(f"자동 로그인 실패: {e}")
            if os.getenv("GITHUB_ACTIONS"):
                return False

    # 로컬 실행 시 수동 로그인 지원
    print("브라우저 창에서 로그인을 직접 완료해 주세요 (300초 대기)...")
    try:
        WebDriverWait(driver, 300).until(
            lambda d: "login" not in d.current_url.lower() and d.current_url != NICEPARK_URL
        )
        print("로그인 확인 완료!")
        return True
    except:
        return False

def run_bot():
    print(f"나이스파크 자동화 봇을 시작합니다... (Server: {FLASK_SERVER_URL})")
    
    chrome_options = Options()
    if os.getenv("GHA_MODE") == "true" or os.getenv("GITHUB_ACTIONS"):
        print("Headless 모드로 실행합니다.")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        # SSL 인증서 오류 무시 (필요 시)
        chrome_options.add_argument("--ignore-certificate-errors")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 10)
    
    try:
        if not login_nicepark(driver, wait):
            print("로그인에 실패했습니다. 종료합니다.")
            return

        while True:
            # 2. 처리 대기 목록 가져오기
            data = get_pending_discounts()
            if data and data['count'] > 0:
                print(f"처리 대기 항목 {data['count']}건 발견")
                
                for item in data['items']:
                    log_id = item['id']
                    car_number = item['car_number']
                    stay_hours = item['stay_hours']
                    
                    print(f"차량 처리 중: {car_number} ({stay_hours})")
                    
                    try:
                        # 3. 나이스파크 할인 적용 로직
                        last_4 = car_number.replace(" ", "")[-4:]
                        print(f"키패드 입력 중: {last_4}")
                        
                        for digit in last_4:
                            digit_int = int(digit)
                            uuid_suffix = 140 + (digit_int - 1) * 2 if digit_int != 0 else 158
                            digit_btn_id = f"mf_wfm_body_wq_uuid_{uuid_suffix}"
                            
                            try:
                                wait.until(EC.element_to_be_clickable((By.ID, digit_btn_id))).click()
                                time.sleep(0.5)
                            except:
                                driver.find_element(By.XPATH, f"//a[text()='{digit}']").click()
                        
                        # 확인(OK) 버튼 클릭
                        ok_btn_id = "mf_wfm_body_wq_uuid_162"
                        wait.until(EC.element_to_be_clickable((By.ID, ok_btn_id))).click()
                        time.sleep(2)
                        
                        # 할인권 선택
                        tk_idx = "1" # 기본 3시간
                        if "6시간" in stay_hours: tk_idx = "2"
                        elif "2시간" in stay_hours: tk_idx = "0"
                        
                        discount_btn_id = f"mf_wfm_body_gen_dcTkList_{tk_idx}_discountTkGrp"
                        
                        try:
                            wait.until(EC.element_to_be_clickable((By.ID, discount_btn_id))).click()
                            time.sleep(1.5)
                            
                            # 알림 확인
                            try:
                                alert = driver.switch_to.alert
                                print(f"알림 확인: {alert.text}")
                                alert.accept()
                            except:
                                pass
                                
                            if mark_as_discounted(log_id):
                                print(f"성공: {car_number} ({stay_hours}) 할인 처리 완료")
                            else:
                                print(f"경고: {car_number} 처리 상태 업데이트 실패")
                        except Exception as e:
                            print(f"할인권 적용 실패: {e}")
                            # 차량 미검색 시 알림 처리
                            try:
                                # "차량이 검색되지 않았습니다" 팝업 확인 (WebSquare용 OK 버튼 등)
                                # 여기서는 단순 status=not_found 처리
                                mark_as_discounted(log_id, status='not_found')
                                print(f"차량 미검색 처리 완료 (ID {log_id})")
                            except:
                                pass
                            
                    except Exception as e:
                        print(f"차량 처리 중 오류 (ID {log_id}): {e}")
            
            if RUN_ONCE:
                print("RUN_ONCE 설정에 따라 봇을 종료합니다.")
                break
                
            # 주기적 체크 (로컬 모드)
            time.sleep(15)
            
    except KeyboardInterrupt:
        print("봇을 종료합니다.")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_bot()
