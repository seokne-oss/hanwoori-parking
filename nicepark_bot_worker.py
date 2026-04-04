"""
Railway Worker: 나이스파크 봇 스케줄러
- 일요일 KST 07:00 ~ 22:00 동안 5분 간격으로 봇 실행
- 봇 실행 전 대기 항목이 있는지 API를 먼저 확인하여 불필요한 Chrome 실행 방지
- Railway Worker 서비스로 배포 (항상 실행 상태 유지)
"""
import subprocess
import sys
import os
import time
import requests
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
FLASK_SERVER_URL = os.environ.get("FLASK_SERVER_URL", "http://127.0.0.1:5000")
CHECK_INTERVAL = 300       # 운영시간 중 재실행 간격 (5분)
BOT_TIMEOUT = 280          # 봇 1회 실행 최대 허용 시간 (초)
IDLE_SLEEP = 30 * 60       # 비운영시간 슬립 단위 (30분)


def now_kst():
    return datetime.now(KST)


def is_operating_hours():
    """현재 KST 기준 일요일 07:00 ~ 21:59 인지 확인"""
    n = now_kst()
    return n.weekday() == 6 and 7 <= n.hour < 22


def seconds_until_next_operating():
    """다음 운영 시작 시각(다음 일요일 07:00 KST)까지 남은 초 반환"""
    n = now_kst()
    days_ahead = (6 - n.weekday()) % 7
    if days_ahead == 0 and n.hour >= 22:
        days_ahead = 7
    next_start = n.replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
    return max(60, (next_start - n).total_seconds())


def has_pending_discounts():
    """Flask 서버에 처리 대기 항목이 있는지 가볍게 확인 (Chrome 실행 전 조기 종료용)"""
    try:
        resp = requests.get(f"{FLASK_SERVER_URL}/api/pending-discounts", timeout=10)
        if resp.status_code == 200:
            return resp.json().get("count", 0) > 0
    except Exception as e:
        print(f"  [사전확인] 서버 연결 실패: {e} → 안전하게 봇 실행 진행")
    return True  # 확인 불가 시 봇을 실행하여 직접 확인


def run_bot_once():
    """nicepark_bot_action.py를 RUN_ONCE=true로 서브프로세스 실행"""
    env = os.environ.copy()
    env["RUN_ONCE"] = "true"

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "nicepark_bot_action.py")],
            env=env,
            timeout=BOT_TIMEOUT,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"  [경고] 봇이 {BOT_TIMEOUT}초 내에 완료되지 않아 강제 종료합니다.")
        return -1
    except Exception as e:
        print(f"  [오류] 봇 실행 중 예외: {e}")
        return -1


# ── 메인 루프 ──────────────────────────────────────────────────────────────────
print(f"[{now_kst().strftime('%Y-%m-%d %H:%M:%S')} KST] Railway Worker 시작 (5분 간격 / 일요일 07~22시)")

while True:
    ts = now_kst().strftime("%H:%M:%S")

    if is_operating_hours():
        if has_pending_discounts():
            print(f"[{ts} KST] 운영시간 & 대기항목 있음 → 봇 실행")
            rc = run_bot_once()
            print(f"[{now_kst().strftime('%H:%M:%S')} KST] 봇 완료 (종료코드: {rc}) → {CHECK_INTERVAL // 60}분 후 재확인")
        else:
            print(f"[{ts} KST] 운영시간 & 대기항목 없음 → {CHECK_INTERVAL // 60}분 후 재확인")
        time.sleep(CHECK_INTERVAL)
    else:
        secs = seconds_until_next_operating()
        sleep_secs = min(secs, IDLE_SLEEP)
        print(
            f"[{now_kst().strftime('%Y-%m-%d %H:%M:%S')} KST] 비운영시간 "
            f"→ 다음 운영까지 {secs / 3600:.1f}시간 / {sleep_secs // 60:.0f}분 후 재확인"
        )
        time.sleep(sleep_secs)
