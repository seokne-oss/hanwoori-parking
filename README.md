# 🚗 한우리교회 주차 등록 시스템

대한예수교장로회 한우리교회 주차 등록 및 관리 웹 애플리케이션입니다.

## 주요 기능

- **교인 주차 등록**: 이름, 연락처, 차량번호, 주차 예정 시간 등록
- **중복 등록 방지**: 동일 차량번호/연락처의 24시간 내 중복 등록 차단
- **차량번호 유효성 검사**: 한국 차량번호 형식 실시간 검증
- **관리자 페이지**: 등록 현황 실시간 확인 및 처리 상태 관리
- **나이스파크 연동**: 자동화 봇을 통한 주차 할인권 자동 적용

## 기술 스택

- **Backend**: Python, Flask, SQLAlchemy
- **Database**: SQLite
- **Frontend**: HTML, Bootstrap 5, JavaScript
- **자동화**: Selenium, webdriver-manager

## 설치 및 실행

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 서버 실행
```bash
python app.py
```

### 3. 접속
- **주차 등록**: http://localhost:5000
- **관리자 페이지**: http://localhost:5000/admin

## 나이스파크 자동화 봇

주차 할인권을 자동으로 적용하는 별도 봇 프로그램입니다.

```bash
python nicepark_bot.py
```

실행 시 브라우저가 열리면 나이스파크 사이트에 직접 로그인해 주세요.  
로그인 완료 후, 관리자가 '완료하기'를 누른 차량에 자동으로 할인권이 적용됩니다.

## 환경 변수

보안을 위해 `.env` 파일을 생성하여 아래 값을 설정하는 것을 권장합니다:

```
SECRET_KEY=your-secret-key
ADMIN_PASSWORD=your-admin-password
```

## 주의사항

- `parking.db`는 실제 교인 데이터가 포함되므로 절대 공개 저장소에 업로드하지 마세요.
- 관리자 비밀번호는 운영 환경에서 반드시 변경해 주세요.
