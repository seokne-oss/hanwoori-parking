import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def debug_popup_close():
    # 현재 실행 중인 브라우저에 연결할 수 없으므로, 
    # USER에게 이 코드를 nicepark_bot_local.py의 특정 위치에 삽입하거나 
    # 별도로 실행하여 결과를 확인하게 유도합니다.
    
    # [가정] 드라이버가 이미 로드된 상태라고 보고 로직만 작성
    # 실제 반영할 강력한 탐색 로직:
    
    print("\n" + "="*50)
    print("[디버그] '닫기' 버튼 정밀 탐색 시작")
    print("="*50)
    
    # 1. 텍스트가 '닫기'인 모든 요소 찾기
    elements = driver.find_elements(By.XPATH, "//*[contains(text(), '닫기')]")
    print(f"-> '닫기' 텍스트 포함 요소 총 {len(elements)}개 발견")
    
    for idx, el in enumerate(elements):
        try:
            tag = el.tag_name
            cid = el.get_attribute("id")
            cls = el.get_attribute("class")
            is_disp = el.is_displayed()
            
            print(f"[{idx}] Tag: {tag}, ID: {cid}, Class: {cls}, Visible: {is_disp}")
            
            if is_disp:
                # 2. 해당 요소의 부모/조상 중 클릭 가능한 트리거가 있는지 확인
                # WebSquare는 보통 부모 'a'나 'div'에 이벤트가 걸림
                print(f"   [시도] {idx}번 요소 및 조상 요소 강제 클릭 시도...")
                
                # 자신 클릭
                driver.execute_script("arguments[0].click();", el)
                
                # 조상 클릭 (최대 3단계 위까지)
                parent = el
                for i in range(1, 4):
                    parent = driver.execute_script("return arguments[0].parentNode;", parent)
                    p_tag = parent.tag_name
                    p_cls = parent.get_attribute("class")
                    if p_tag in ['a', 'div', 'button']:
                        print(f"   [시도] {idx}번의 조상 {i}단계({p_tag}.{p_cls}) 클릭")
                        driver.execute_script("arguments[0].click();", parent)
                
        except Exception as e:
            print(f"[{idx}] 확인 중 오류: {e}")

    # 3. 우측 상단 'X' 버튼이 있는지 별도 확인
    print("\n[디버그] 우측 상단 'X' 버튼(w2window_close) 탐색")
    x_btns = driver.find_elements(By.XPATH, "//*[contains(@class, 'w2window_close')] | //*[contains(@id, 'close')]")
    for x in x_btns:
        if x.is_displayed():
            print(f"-> 'X' 버튼 발견! ID: {x.get_attribute('id')}, 클릭 시도")
            driver.execute_script("arguments[0].click();", x)

    print("="*50 + "\n")

# 이 로직을 봇에 이식하겠습니다.
