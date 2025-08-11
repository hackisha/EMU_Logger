# -*- coding: utf-8 -*-

import os

# ===================== 공통 설정 =====================
LOG_DIR = "/home/pi/can_logger/logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ===================== CAN 설정 =====================
CAN_CHANNEL = "can0"
CAN_BITRATE = 1_000_000  # 1 Mbps
EMU_ID_BASE = 0x600

# FRAME_0 ~ FRAME_7
EMU_IDS = {f"FRAME_{i}": EMU_ID_BASE + i for i in range(8)}

# ===================== GPS 설정 =====================
SERIAL_PORT = "/dev/serial0"
BAUD_RATE = 9600

# ===================== GPIO 핀 (BCM) =================
BUTTON_PIN = 17        # 로깅 시작/정지 토글 버튼
LOGGING_LED_PIN = 27   # 로깅 상태 LED
ERROR_LED_PIN = 22     # 오류 LED
WIFI_LED_PIN = 5       # Wi‑Fi 상태 LED

# ===================== Firebase 설정 =================
# Realtime Database URL 예: "https://<project-id>.firebaseio.com/"
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL", "").rstrip("/")
# DB Secret 또는 사용자 토큰(선택). 없으면 인증 없이 공개 규칙에 따름
FIREBASE_AUTH = os.environ.get("FIREBASE_AUTH", "") or None

# 경로 정의 (원하면 수정)
FB_PATHS = {
    "CAN_REALTIME": "/realtime/can",     # 최근 CAN 상태 (PATCH)
    "GPS_REALTIME": "/realtime/gps",     # 최근 GPS 상태 (PATCH)
    "CAN_TIMESERIES": "/timeseries/can", # 시계열(POST)
    "GPS_TIMESERIES": "/timeseries/gps", # 시계열(POST)
}

# Firebase 사용 on/off (테스트시 끌 수 있음)
FIREBASE_ENABLE = True
