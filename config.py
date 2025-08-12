# -*- coding: utf-8 -*-
import os

# ===================== 공통 =====================
LOG_DIR = "/home/pi/can_logger/logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ===================== CAN =====================
CAN_CHANNEL = "can0"
CAN_BITRATE = 1_000_000
EMU_ID_BASE = 0x600
EMU_IDS = {f"FRAME_{i}": EMU_ID_BASE + i for i in range(8)}

# ===================== GPS =====================
SERIAL_PORT = "/dev/serial0"
BAUD_RATE = 9600

# ===================== GPIO (BCM) =================
BUTTON_PIN = 17
LOGGING_LED_PIN = 27
ERROR_LED_PIN = 22
WIFI_LED_PIN = 5

# ===================== Firebase =================
# 모듈화 전과 호환: 웹/기존 코드가 구독하던 경로는 "emu_realtime_data"
# 아래 기본 URL은 프로젝트에 맞게 환경변수로 덮어쓰기 가능
FIREBASE_DB_URL = os.environ.get(
    "FIREBASE_DB_URL",
    "https://emucanlogger-default-rtdb.firebaseio.com"
).rstrip("/")

# 인증 토큰(선택). 공개 규칙이면 비워도 됨.
FIREBASE_AUTH = os.environ.get("FIREBASE_AUTH", "") or None

# Firebase ON/OFF 스위치(테스트용)
FIREBASE_ENABLE = True

# 웹 호환을 위한 레거시 실시간 경로
LEGACY_REALTIME_KEY = "emu_realtime_data"   # ← 모듈화 전과 동일

# 시계열 저장 루트(예전 스크립트 일부가 /logs 사용)
TIMESERIES_ROOT = "/logs"

# 경로 매핑
# - 실시간(CAN/GPS/ACC)은 전부 emu_realtime_data로 병합 패치
# - 시계열은 필요 시 /logs/* 로 보관(웹 호환엔 영향 없음)
FB_PATHS = {
    # 실시간(모두 같은 노드로 병합 → 웹과 완전 호환)
    "LEGACY_REALTIME": f"/{LEGACY_REALTIME_KEY}",
    "CAN_REALTIME":    f"/{LEGACY_REALTIME_KEY}",
    "GPS_REALTIME":    f"/{LEGACY_REALTIME_KEY}",
    "ACC_REALTIME":    f"/{LEGACY_REALTIME_KEY}",

    # 시계열(원하면 대시보드에서 활용 가능; 웹 호환 필수는 아님)
    "CAN_TIMESERIES": f"{TIMESERIES_ROOT}/can",
    "GPS_TIMESERIES": f"{TIMESERIES_ROOT}/gps",
    "ACC_TIMESERIES": f"{TIMESERIES_ROOT}/acc",
}

# ===================== 기타 옵션 =================
# 콘솔에 수신 NMEA 원문/요약 출력(원하면 False)
GPS_VERBOSE = True
