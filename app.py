# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, time, timezone, timedelta
import os
import re

# 현재 파일의 디렉토리 경로를 기반으로 데이터베이스 경로 설정
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# 보안을 위해 실제 운영 시에는 더 복잡한 키로 변경해야 합니다.
app.config['SECRET_KEY'] = 'hanwoori-church-parking-secret-key-2023'
# SQLite 데이터베이스 설정 (프로젝트 폴더 내에 생성됨)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'parking.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# --- 데이터베이스 모델 (테이블) 정의 ---
class ParkingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    car_number = db.Column(db.String(20), nullable=False)
    stay_hours = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    remarks = db.Column(db.String(100), nullable=True)
    is_processed = db.Column(db.Boolean, default=False, nullable=False)
    is_discounted = db.Column(db.Boolean, default=False, nullable=False)
    entry_time = db.Column(db.String(20), nullable=True)

    def get_status(self):
        """통합 상태 정보를 반환합니다."""
        if not self.is_processed:
            return {'text': '미처리', 'class': 'secondary', 'bg': 'secondary'}
        
        if self.is_discounted:
            return {'text': '주차처리완료', 'class': 'success', 'bg': 'success'}
        
        if self.remarks and '[차량번호 확인 안됨]' in self.remarks:
            return {'text': '차량번호 확인 안됨', 'class': 'danger', 'bg': 'danger'}
        
        return {'text': '차량번호 확인 중', 'class': 'warning', 'bg': 'warning'}

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))

# gunicorn 등 외부 실행 환경에서도 DB 테이블을 자동 생성
with app.app_context():
    db.create_all()
    # 초기 설정값 생성 (없을 경우)
    if not SystemSetting.query.filter_by(key='service_mode').first():
        db.session.add(SystemSetting(key='service_mode', value='auto_sunday', description='서비스 운영 모드 (manual_on, manual_off, auto_sunday)'))
        db.session.commit()

# --- 서비스 가동 시간 체크 미들웨어 ---
@app.before_request
def check_service_availability():
    # 관리자 페이지, 정적 파일, API, 안내 페이지는 체크 제외
    exempt_paths = ['/admin', '/login', '/logout', '/static', '/api', '/service-unavailable', '/create_test_data']
    if any(request.path.startswith(path) for path in exempt_paths):
        return None

    # 서비스 모드 확인
    mode_setting = SystemSetting.query.filter_by(key='service_mode').first()
    mode = mode_setting.value if mode_setting else 'auto_sunday'

    if mode == 'manual_on':
        return None
    elif mode == 'manual_off':
        return redirect(url_for('service_unavailable'))
    else: # auto_sunday
        # 한국 시간 기준 요일 확인 (0: 월, 6: 일)
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        if now_kst.weekday() == 6: # 일요일
            return None
        else:
            return redirect(url_for('service_unavailable'))

@app.route('/service-unavailable')
def service_unavailable():
    return render_template('service_unavailable.html')

# --- 라우트(URL) 및 기능 정의 ---

# 0. 관리자 로그인/로그아웃
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        # 실제 운영 시에는 환경 변수 등 더 안전한 방법으로 비밀번호를 관리해야 합니다.
        if password == 'hanwoori1234':
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            flash('비밀번호가 올바르지 않습니다.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('성공적으로 로그아웃되었습니다.', 'info')
    return redirect(url_for('login'))


# 1. 성도용 입력 페이지 (GET: 페이지 보여주기, POST: 데이터 저장)
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        car_number = request.form.get('car_number')
        stay_hours = request.form.get('stay_hours')
        remarks = request.form.get('remarks')

        # 간단한 유효성 검사
        if not all([name, phone, car_number, stay_hours]):
            flash('모든 항목을 정확히 입력해주세요.', 'danger')
            return redirect(url_for('index'))

        # 차량 번호 유효성 검사 (한국 차량 번호 형식)
        # 예: 12가 1234, 123가 1234, 서울12 가 1234 등
        car_pattern = re.compile(r'^(\d{2,3}|[가-힣]{2}\d{2})\s?[가-힣]\s?\d{4}$')
        if not car_pattern.match(car_number):
            flash('올바른 차량 번호 형식이 아닙니다. (예: 12가 3456)', 'danger')
            return redirect(url_for('index'))

        # 중복 등록 확인 (최근 24시간 내 동일 차량 번호와 전화번호)
        kst = timezone(timedelta(hours=9))
        one_day_ago = datetime.now(kst) - timedelta(days=1)
        
        duplicate = ParkingLog.query.filter(
            ParkingLog.car_number == car_number,
            ParkingLog.phone == phone,
            ParkingLog.created_at >= one_day_ago
        ).first()

        if duplicate:
            flash(f'이미 등록된 차량입니다. ({duplicate.created_at.strftime("%H:%M")} 등록됨)', 'warning')
            return redirect(url_for('status', phone=phone))

        new_log = ParkingLog(
            name=name,
            phone=phone,
            car_number=car_number,
            stay_hours=stay_hours,
            remarks=remarks,
            created_at=datetime.now(timezone(timedelta(hours=9))) # 한국 시간(KST)으로 저장
        )
        db.session.add(new_log)
        db.session.commit()

        flash(f'주차 정보가 성공적으로 등록되었습니다. <a href="{url_for("status", phone=phone)}" class="alert-link">내 등록 현황 확인하기</a>', 'success')
        return redirect(url_for('index'))

    return render_template('index.html')

# 2. 봉사자용 관리 페이지
@app.route('/admin')
def admin():
    # 로그인 상태가 아니면 로그인 페이지로 리디렉션
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # 한국 시간 기준으로 오늘 날짜의 데이터만 가져오기
    kst = timezone(timedelta(hours=9))
    today_kst = datetime.now(kst).date()
    today_start = datetime.combine(today_kst, time.min)

    # 어제 자정부터 데이터를 조회하도록 시작 시간 변경
    view_start_time = today_start - timedelta(days=1)
    
    today_logs = ParkingLog.query.filter(ParkingLog.created_at >= view_start_time).order_by(ParkingLog.is_processed.asc(), ParkingLog.created_at.asc()).all()
    past_logs = ParkingLog.query.filter(ParkingLog.created_at < view_start_time).order_by(ParkingLog.is_processed.asc(), ParkingLog.created_at.asc()).all()
    
    # 상태별 그룹화 (템플릿 복잡도 감소 및 오류 방지)
    unconfirmed_logs = [log for log in today_logs if not log.is_processed]
    checking_logs = []
    not_found_logs = []
    completed_logs = []
    
    for log in today_logs:
        if log.is_processed:
            if log.is_discounted:
                completed_logs.append(log)
            else:
                if log.remarks and '[차량번호 확인 안됨]' in log.remarks:
                    not_found_logs.append(log)
                else:
                    checking_logs.append(log)
    
    # VSCode 편집기 오류 방지를 위해 SVG 코드를 변수로 전달
    copy_icon_svg = '<svg class="icon-copy" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z"></path><path d="M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zM-1 7a.5.5 0 0 1 .5-.5h1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-1a.5.5 0 0 1-.5-.5v-1zM8 1.5A1.5 1.5 0 0 0 6.5 0h-3A1.5 1.5 0 0 0 2 1.5v1A1.5 1.5 0 0 0 3.5 4h3A1.5 1.5 0 0 0 8 2.5v-1z"></path></svg>'

    # 서비스 모드 정보 추가
    service_mode = SystemSetting.query.filter_by(key='service_mode').first()
    service_mode_value = service_mode.value if service_mode else 'auto_sunday'

    return render_template('admin.html', 
                          today_logs=today_logs, 
                          past_logs=past_logs, 
                          unconfirmed_logs=unconfirmed_logs,
                          checking_logs=checking_logs,
                          not_found_logs=not_found_logs,
                          completed_logs=completed_logs,
                          copy_icon_svg=copy_icon_svg,
                          service_mode=service_mode_value)

# 4. 성도용 상태 조회 페이지
@app.route('/status', methods=['GET'])
def status():
    phone = request.args.get('phone')
    logs = []
    if phone:
        # 오늘 날짜에 해당 전화번호로 등록된 가장 최신 기록을 찾음
        kst = timezone(timedelta(hours=9))
        today_kst = datetime.now(kst).date()
        today_start = datetime.combine(today_kst, time.min)
        # 어제 자정부터 데이터를 조회하도록 시작 시간 변경
        view_start_time = today_start - timedelta(days=1)
        logs = ParkingLog.query.filter(
            ParkingLog.phone == phone,
            ParkingLog.created_at >= view_start_time
        ).order_by(ParkingLog.created_at.desc()).all()

        if not logs:
            flash(f"'{phone}' 번호로 최근 등록된 주차 정보가 없습니다.", 'warning')

    return render_template('status.html', logs=logs, phone=phone)


@app.route('/admin/process/<int:log_id>', methods=['POST'])
def process_log(log_id):
    # 로그인 상태가 아니면 접근 거부
    if not session.get('logged_in'):
        return {'status': 'error', 'message': 'Unauthorized'}, 401

    log = ParkingLog.query.get_or_404(log_id)
    
    # '확인 중', '완료', '확인 안됨' 그룹에서 호출된 경우 -> '미확인(봉사자 확인 전)' 상태로 완전 초기화
    if log.is_processed:
        # 모든 처리 상태를 초기화하여 '미확인 항목' 섹션으로 되돌림
        log.is_processed = False
        log.is_discounted = False
        log.entry_time = None
        # 실패 메모 제거
        if log.remarks:
            log.remarks = log.remarks.replace("[차량번호 확인 안됨]", "").strip()
        print(f"   [초기화] {log.car_number} 항목을 '미확인' 상태로 완전 되돌림")
    else:
        # 미확인 항목에서 '확인'을 누른 경우 -> 승인(is_processed=True)
        log.is_processed = True
    
    db.session.commit()
    return {'status': 'success', 'is_processed': log.is_processed, 'is_discounted': log.is_discounted}

# 4-1. 설정 변경 API
@app.route('/admin/update_setting', methods=['POST'])
def update_setting():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    key = request.form.get('key')
    value = request.form.get('value')
    
    setting = SystemSetting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
        db.session.commit()
        flash(f'설정이 변경되었습니다: {value}', 'success')
    else:
        flash('존재하지 않는 설정 키입니다.', 'danger')
        
    return redirect(url_for('admin'))


# 5. 이전 기록 삭제 기능
@app.route('/admin/delete_old', methods=['POST'])
def delete_old_logs():
    # 로그인 상태가 아니면 접근 거부
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    try:
        # 한국 시간 기준으로 오늘 자정 이전의 모든 기록을 찾아서 삭제
        kst = timezone(timedelta(hours=9))
        today_kst = datetime.now(kst).date()
        today_start = datetime.combine(today_kst, time.min)
        
        num_deleted = ParkingLog.query.filter(ParkingLog.created_at < today_start).delete()
        db.session.commit()
        flash(f'오늘 이전의 주차 기록 {num_deleted}건이 삭제되었습니다.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'기록 삭제 중 오류가 발생했습니다: {e}', 'danger')
    return redirect(url_for('admin'))

# 6. (테스트용) 과거 데이터 생성 기능
@app.route('/create_test_data')
def create_test_data():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    try:
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst)
        
        # 봇이 처리하기 전인 '미승인(is_processed=False)' 상태의 테스트 데이터 5건 생성
        test_cars = [
            ("홍길동", "010-1234-5678", "12가 3456", "3시간"),
            ("성춘향", "010-2222-3333", "123하 4567", "6시간"),
            ("이몽룡", "010-5555-6666", "서울12 가 1234", "2시간"),
            ("임꺽정", "010-9999-8888", "55오 5555", "3시간"),
            ("심청이", "010-1111-0000", "99가 9999", "3시간")
        ]

        for name, phone, car, hours in test_cars:
            new_log = ParkingLog(
                name=name, 
                phone=phone, 
                car_number=car, 
                stay_hours=hours, 
                is_processed=False, # 미승인 상태
                is_discounted=False,
                created_at=now
            )
            db.session.add(new_log)
        
        db.session.commit()
        flash(f'미승인 상태의 테스트 데이터 {len(test_cars)}건이 생성되었습니다.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'테스트 데이터 생성 중 오류 발생: {e}', 'danger')

    return redirect(url_for('admin'))

# 7. (관리자용) 전체 데이터 삭제 기능
@app.route('/admin/delete_all', methods=['POST'])
def delete_all_data():
    # 로그인 상태가 아니면 접근 거부
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    try:
        num_deleted = db.session.query(ParkingLog).delete()
        db.session.commit()
        flash(f'모든 주차 기록 {num_deleted}건이 영구적으로 삭제되었습니다.', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'전체 기록 삭제 중 오류가 발생했습니다: {e}', 'danger')
    
    # 테스트 데이터 생성 후에는 테스트 데이터가 바로 보이도록 admin 페이지로 리디렉션
    return redirect(url_for('admin'))


# --- 자동화 봇용 API ---

@app.route('/api/pending-discounts', methods=['GET'])
def get_pending_discounts():
    # 처리 완료되었으나 할인은 아직 적용되지 않은 오늘/최근 기록 조회
    kst = timezone(timedelta(hours=9))
    one_day_ago = datetime.now(kst) - timedelta(days=1)
    
    # 봉사자가 '확인'을 눌렀고(is_processed), 아직 할인 전이며(is_discounted=False), 
    # 차량번호 미확인 오류([차량번호 확인 안됨])가 없는 '확인 중' 상태의 데이터만 조회
    pending = ParkingLog.query.filter(
        ParkingLog.is_processed == True,
        ParkingLog.is_discounted == False,
        (ParkingLog.remarks == None) | (~ParkingLog.remarks.contains('[차량번호 확인 안됨]')),
        ParkingLog.created_at >= one_day_ago
    ).all()
    
    return {
        'count': len(pending),
        'items': [{
            'id': p.id,
            'car_number': p.car_number,
            'full_car_number': p.car_number, # 호환성을 위해 추가
            'stay_hours': p.stay_hours,
            'name': p.name
        } for p in pending]
    }

@app.route('/api/mark-discounted/<int:log_id>', methods=['POST'])
def mark_discounted(log_id):
    # JSON 바디 또는 폼 데이터에서 정보 추출
    data = request.json if request.is_json else request.form
    status = data.get('status', 'success')
    entry_time = data.get('entry_time')
    
    log = ParkingLog.query.get_or_404(log_id)
    if status == 'not_found':
        log.is_discounted = False
        log.remarks = (log.remarks + " [차량번호 확인 안됨]") if log.remarks else "[차량번호 확인 안됨]"
    else:
        log.is_discounted = True
        if entry_time:
            log.entry_time = entry_time
        
    db.session.commit()
    return {'status': 'success', 'log_id': log_id, 'result': status, 'entry_time': log.entry_time}


# --- 애플리케이션 실행 ---
if __name__ == '__main__':
    import os
    print("스크립트 실행 시작...")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    print(f"Flask 서버를 시작합니다... (port={port}, debug={debug})")
    app.run(debug=debug, host='0.0.0.0', port=port)
