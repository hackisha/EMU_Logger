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
FIREBASE_DB_URL = os.environ.get("FIREBASE_DB_URL", "https://emucanlogger-default-rtdb.firebaseio.com").rstrip("/")
FIREBASE_AUTH = os.environ.get("FIREBASE_AUTH", "") or None
FIREBASE_ENABLE = True

# 경로 정의
FB_PATHS = {
    "CAN_REALTIME": "/realtime/can",
    "GPS_REALTIME": "/realtime/gps",
    "ACC_REALTIME": "/realtime/acc",
    "CAN_TIMESERIES": "/timeseries/can",
    "GPS_TIMESERIES": "/timeseries/gps",
    "ACC_TIMESERIES": "/timeseries/acc",
    "LEGACY_REALTIME": "/emu_realtime_data",
}
