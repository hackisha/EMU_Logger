# -*- coding: utf-8 -*-

import os
import sys
import csv
import signal
import time
import threading
from datetime import datetime

from .config import (
    LOG_DIR, SERIAL_PORT, BAUD_RATE,
    EMU_IDS, FB_PATHS
)
from .firebase_client import FirebaseClient
from .gpio_ctrl import GpioController
from .can_worker import CanWorker
from .gps_worker import GpsWorker
from .wifi_monitor import start_wifi_monitor
from .accel_worker import AccelWorker  # ← 추가

# ======== 전역 상태 ========
exit_event = threading.Event()
logging_active = False

latest_can_data = {}
latest_gps_data = {}
latest_acc_data = {}  # ← 추가

csv_file = None
csv_writer = None
last_button_ts = 0.0

def ensure_root():
    if os.geteuid() != 0:
        print("오류: 이 스크립트는 sudo 권한으로 실행해야 합니다.")
        sys.exit(1)

def patch_legacy_realtime(fb: FirebaseClient):
    """
    웹(gps.html)이 구독하는 emu_realtime_data 경로에
    CAN + GPS + ACC 데이터를 병합해 패치.
    키 호환을 위해 lat/lon 별칭도 포함.
    """
    merged = {}
    merged.update(latest_can_data)
    merged.update(latest_gps_data)
    merged.update(latest_acc_data)

    # 웹에서 기대하는 필드 별칭 맞춤
    # GPSWorker는 Latitude/Longitude 키를 사용 → lat/lon 별칭 생성
    if "Latitude" in merged and "Longitude" in merged:
        merged.setdefault("lat", merged["Latitude"])
        merged.setdefault("lon", merged["Longitude"])

    # 고도/방향(있다면)도 다양한 별칭 제공
    if "Altitude" in merged:
        merged.setdefault("altitude", merged["Altitude"])
        merged.setdefault("gps_alt", merged["Altitude"])
    if "Heading" in merged:
        merged.setdefault("heading", merged["Heading"])
        merged.setdefault("course", merged["Heading"])

    # 타임스탬프 추가
    merged["ts"] = fb.now_ms()

    fb.patch(FB_PATHS["LEGACY_REALTIME"], merged)

def on_can_parsed(arbitration_id: int, parsed: dict, fb: FirebaseClient, gpio: GpioController):
    """CAN 수신 시 호출: 최신 상태 갱신 + CSV 기록 트리거 + 레거시 병합 패치"""
    global latest_can_data, csv_writer, csv_file
    latest_can_data.update(parsed)

    # 병합 패치(웹 실시간 반영)
    patch_legacy_realtime(fb)

    # FRAME_0가 들어올 때 한 줄 기록 (원본 로직 유지)
    if logging_active and csv_writer and arbitration_id == EMU_IDS["FRAME_0"]:
        row = {"Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}
        row.update(latest_gps_data)
        row.update(latest_can_data)
        row.update(latest_acc_data)  # ← 가속도도 CSV에 포함(원하면 제거 가능)
        csv_writer.writerow(row)
        csv_file.flush()
        gpio.blink_logging_led_once(50)

def on_gps_update(gps_parsed: dict, fb: FirebaseClient):
    """GPS 갱신 시 호출: 최신 GPS 상태 + 레거시 병합 패치"""
    global latest_gps_data
    latest_gps_data.update(gps_parsed)
    patch_legacy_realtime(fb)

def on_acc_update(acc_parsed: dict, fb: FirebaseClient):
    """ACC 갱신 시 호출: 최신 ACC 상태 + 레거시 병합 패치"""
    global latest_acc_data
    latest_acc_data.update(acc_parsed)
    patch_legacy_realtime(fb)

def toggle_logging(gpio: GpioController):
    """버튼 토글 처리: CSV 시작/종료 및 LED 상태"""
    global logging_active, csv_file, csv_writer
    logging_active = not logging_active

    if logging_active:
        gpio.set_logging_led(True)
        csv_filename = f"{LOG_DIR}/datalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        print(f"\n버튼: 로깅 시작 → {csv_filename}")
        csv_file = open(csv_filename, "w", newline="")
        fieldnames = [
            "Timestamp", "Latitude", "Longitude", "GPS_Speed_KPH", "Satellites",
            "RPM", "TPS_percent", "IAT_C", "MAP_kPa", "PulseWidth_ms",
            "AnalogIn1_V", "AnalogIn2_V", "AnalogIn3_V", "AnalogIn4_V",
            "VSS_kmh", "Baro_kPa", "OilTemp_C", "OilPressure_bar", "FuelPressure_bar", "CLT_C",
            "IgnAngle_deg", "DwellTime_ms", "WBO_Lambda", "LambdaCorrection_percent", "EGT1_C", "EGT2_C",
            "Gear", "EmuTemp_C", "Batt_V", "CEL_Error", "Flags1", "Ethanol_percent",
            "DBW_Pos_percent", "DBW_Target_percent", "TC_drpm_raw", "TC_drpm", "TC_TorqueReduction_percent", "PitLimit_TorqueReduction_percent",
            "AnalogIn5_V", "AnalogIn6_V", "OutFlags1", "OutFlags2", "OutFlags3", "OutFlags4",
            "BoostTarget_kPa", "PWM1_DC_percent", "DSG_Mode", "LambdaTarget", "PWM2_DC_percent", "FuelUsed_L",
            # 가속도 추가
            "ax_g", "ay_g", "az_g"
        ]
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        csv_writer.writeheader()
    else:
        print("\n버튼: 로깅 종료")
        gpio.set_logging_led(False)
        if csv_file:
            name = csv_file.name
            csv_file.close()
            print(f"로그 저장 완료: {name}")
            csv_file = None
            csv_writer = None

def handle_exit(signum, frame):
    print("\n종료 신호 수신. 안전 종료 중...")
    exit_event.set()

def run():
    global last_button_ts
    ensure_root()

    fb = FirebaseClient()
    gpio = GpioController()

    # 콜백에 객체 바인딩
    def _can_cb(arbid, parsed): return on_can_parsed(arbid, parsed, fb, gpio)
    def _gps_cb(parsed):       return on_gps_update(parsed, fb)
    def _acc_cb(parsed):       return on_acc_update(parsed, fb)

    canw = CanWorker(on_parsed=_can_cb, fb=fb)
    gpsw = GpsWorker(serial_port=SERIAL_PORT, baudrate=BAUD_RATE, on_update=_gps_cb, fb=fb)
    accw = AccelWorker(i2c_bus=1, address=0x53, on_update=_acc_cb, fb=fb)  # I²C-1, 0x53

    # Wi‑Fi LED 모니터
    wifi_thread = start_wifi_monitor(gpio, exit_event)

    # 시작
    print("CAN 인터페이스 활성화 및 버스 열기...")
    canw.start()
    print("GPS 포트 열기...")
    try:
        gpsw.start()
        print(f"GPS 수신 시작: {SERIAL_PORT} @ {BAUD_RATE}")
    except Exception as e:
        print(f"경고: GPS 포트 초기화 실패: {e}")

    print("ADXL345 시작...")
    try:
        accw.start()
        print("ADXL345 준비 완료 (I²C-1, 0x53)")
    except Exception as e:
        print(f"경고: ADXL345 초기화 실패: {e}")

    print("\n대기 중... 버튼을 눌러 로깅을 시작/정지하세요. (종료: Ctrl+C)")

    # 메인 루프
    try:
        while not exit_event.is_set():
            # 버튼 폴링 (디바운스 300ms)
            now = time.time()
            if gpio.read_button_pressed():
                if now - last_button_ts > 0.3:
                    toggle_logging(gpio)
                last_button_ts = now

            # CAN/GPS/ACC 한 사이클씩 돌리기
            canw.recv_once(timeout=0.02)
            gpsw.read_once()
            accw.read_once()

            time.sleep(0.005)

    except Exception as e:
        print(f"\n심각 오류: {e}", file=sys.stderr)
        gpio.set_error_led(True)
    finally:
        exit_event.set()
        try:    canw.shutdown()
        except: pass
        try:    gpsw.shutdown()
        except: pass
        try:    accw.shutdown()
        except: pass

        if csv_file and not csv_file.closed:
            csv_file.close()
        gpio.cleanup()
        print("정리 완료. 프로그램 종료.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    run()
