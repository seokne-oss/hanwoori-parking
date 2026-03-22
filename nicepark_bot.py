
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 설정 사항 ---
FLASK_SERVER_URL = "http://localhost:5000"
NICEPARK_URL = "https://npdc-i.nicepark.co.kr"

def get_pending_discounts():
    try:
        response = requests.get(f"{FLASK_SERVER_URL}/api/pending-discounts")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Flask 서버 연결 실패: {e}")
    return None

def mark_as_discounted(log_id, status='success'):
    try:
        response = requests.post(f"{FLASK_SERVER_URL}/api/mark-discounted/{log_id}", json={'status': status})
        return response.status_code == 200
    except Exception as e:
        print(f"상태 업데이트 실패 (ID: {log_id}): {e}")
    return False

def run_bot():
    print("나이스파크 자동화 봇을 시작합니다...")
    
    # 크롬 드라이버 설정 (백그라운드 실행을 원할 경우 headless 옵션 추가)
    chrome_options = Options()
    # chrome_options.add_argument("--headless") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 10)
    
    try:
        # 1. 나이스파크 접속 및 로그인 대기
        print(f"{NICEPARK_URL}에 접속합니다.")
        print("브라우저 창에서 로그인을 직접 완료해 주세요...")
        driver.get(NICEPARK_URL)
        
        # 사용자가 로그인을 완료하고 메인 페이지(또는 특정 요소)가 나타날 때까지 대기
        # 로그인을 완료하면 '로그아웃' 버튼이 생기거나 URL이 변경되는 것을 감지합니다.
        # 아래는 예시이며, 실제 사이트의 로그인 후 나타나는 요소로 수정 가능합니다.
        try:
            # 주소에 'main'이 포함되거나 특정 요소가 나타날 때까지 최대 5분(300초) 대기
            WebDriverWait(driver, 300).until(
                lambda d: "login" not in d.current_url.lower() and d.current_url != NICEPARK_URL
            )
            print("로그인 확인 완료! 자동화 프로세스를 시작합니다.")
        except Exception as e:
            print("로그인 대기 시간이 초과되었거나 오류가 발생했습니다.")
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
                        # 차량 번호 뒤 4자리를 키패드로 입력함
                        last_4 = car_number.replace(" ", "")[-4:]
                        print(f"키패드 입력 중: {last_4}")
                        
                        for digit in last_4:
                            # 숫자 '1'은 140, '2'는 142 ... '0'은 158
                            digit_int = int(digit)
                            uuid_suffix = 140 + (digit_int - 1) * 2 if digit_int != 0 else 158
                            digit_btn_id = f"mf_wfm_body_wq_uuid_{uuid_suffix}"
                            
                            try:
                                wait.until(EC.element_to_be_clickable((By.ID, digit_btn_id))).click()
                                time.sleep(0.3)
                            except:
                                # ID가 다를 경우를 대비하여 텍스트로 찾기 시도
                                driver.find_element(By.XPATH, f"//a[text()='{digit}']").click()
                        
                        # 확인(OK) 버튼 클릭
                        ok_btn_id = "mf_wfm_body_wq_uuid_162"
                        wait.until(EC.element_to_be_clickable((By.ID, ok_btn_id))).click()
                        time.sleep(1.5)
                        
                        # 할인권 선택 (기본적으로 첫 번째 또는 대상 시간대에 맞는 버튼 클릭)
                        # 2시간: ..._0_..., 3시간: ..._1_..., 6시간: ..._2_...
                        tk_idx = "1" # 기본 3시간
                        if "6시간" in stay_hours: tk_idx = "2"
                        elif "2시간" in stay_hours: tk_idx = "0"
                        
                        discount_btn_id = f"mf_wfm_body_gen_dcTkList_{tk_idx}_discountTkGrp"
                        
                        try:
                            # 할인권 버튼 클릭
                            wait.until(EC.element_to_be_clickable((By.ID, discount_btn_id))).click()
                            time.sleep(1)
                            
                            # 알림창(Alert) 확인 처리
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
                            
                    except Exception as e:
                        print(f"차량 처리 중 오류 (ID {log_id}): {e}")
            
            # 3. 주기적 체크 (예: 10초마다)
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("봇을 종료합니다.")
    finally:
        driver.quit()

if __name__ == "__main__":
    # 필요한 라이브러리 설치 안내: pip install selenium webdriver-manager requests
    run_bot()
