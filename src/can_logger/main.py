# -*- coding: utf-8 -*-

import os
import sys
import csv
import signal
import time
import threading
from datetime import datetime

# --- 설정 파일 및 모듈 임포트 ---
# 실제 환경에서는 아래 .config가 정상적으로 동작해야 합니다.
# 여기서는 예시를 위해 가상 클래스를 만듭니다.
try:
    from .config import (
        LOG_DIR, SERIAL_PORT, BAUD_RATE,
        EMU_IDS, FB_PATHS
    )
    from .firebase_client import FirebaseClient
    from .gpio_ctrl import GpioController
    from .can_worker import CanWorker
    from .gps_worker import GpsWorker
    from .wifi_monitor import start_wifi_monitor
    from .accel_worker import AccelWorker
except ImportError:
    # --- 개발 환경용 가상 클래스 (실제 환경에서는 이 부분이 실행되지 않음) ---
    print("경고: 실제 모듈을 찾을 수 없어 가상 클래스를 사용합니다.", file=sys.stderr)
    LOG_DIR, SERIAL_PORT, BAUD_RATE = "logs", "/dev/ttyS0", 9600
    EMU_IDS, FB_PATHS = {"FRAME_0": 0x600}, {"LEGACY_REALTIME": "emu_realtime_data"}
    class FirebaseClient:
        def patch(self, path, data): pass
        def now_ms(self): return int(time.time() * 1000)
    class GpioController:
        def set_logging_led(self, state): pass
        def blink_logging_led_once(self, duration): pass
        def read_button_pressed(self): return False
        def cleanup(self): pass
        def set_error_led(self, state): pass
    class BaseWorker:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def shutdown(self): pass
    class CanWorker(BaseWorker):
        def recv_once(self, timeout): pass
    class GpsWorker(BaseWorker):
        def read_once(self): pass
    class AccelWorker(BaseWorker):
        def read_once(self): pass
    def start_wifi_monitor(gpio, event):
        def dummy_wifi_thread():
            while not event.is_set():
                time.sleep(1)
        thread = threading.Thread(target=dummy_wifi_thread, daemon=True)
        thread.start()
        return thread
    # --- 가상 클래스 끝 ---


# ======== 전역 상태 변수 ========
exit_event = threading.Event()  # 프로그램 종료 신호
logging_active = False          # 현재 로깅(CSV 저장) 활성화 상태

# 각 센서의 최신 데이터를 저장하는 딕셔너리
latest_can_data = {}
latest_gps_data = {}
latest_acc_data = {}

# CSV 파일 및 쓰기 관련 객체
csv_file = None
csv_writer = None

# 버튼 디바운싱을 위한 타임스탬프
last_button_ts = 0.0


def ensure_root():
    """스크립트가 root 권한으로 실행되었는지 확인합니다."""
    if os.geteuid() != 0:
        print("오류: 이 스크립트는 sudo 권한으로 실행해야 합니다.", file=sys.stderr)
        sys.exit(1)

def patch_legacy_realtime(fb: FirebaseClient):
    """
    웹(gps.html)이 구독하는 경로에 CAN, GPS, ACC 데이터를 병합하여 전송합니다.
    데이터 수신 시마다 호출되지 않고, 메인 루프에서 주기적으로 호출됩니다.
    """
    merged = {}
    merged.update(latest_can_data)
    merged.update(latest_gps_data)
    merged.update(latest_acc_data)

    # 데이터가 하나라도 있어야 전송
    if not merged:
        return

    # 웹 클라이언트와의 호환성을 위한 별칭(alias) 추가
    if "Latitude" in merged: merged.setdefault("lat", merged["Latitude"])
    if "Longitude" in merged: merged.setdefault("lon", merged["Longitude"])
    if "Altitude" in merged: merged.setdefault("altitude", merged["Altitude"])
    if "Heading" in merged: merged.setdefault("heading", merged["Heading"])

    merged["ts"] = fb.now_ms()
    fb.patch(FB_PATHS["LEGACY_REALTIME"], merged)

def on_can_parsed(arbitration_id: int, parsed: dict, gpio: GpioController):
    """
    CAN 데이터 수신 시 호출되는 콜백 함수.
    - 최신 CAN 상태를 전역 변수에 업데이트합니다.
    - 로깅이 활성화된 경우, 특정 CAN ID(FRAME_0) 수신 시 CSV에 한 줄 기록합니다.
    """
    global latest_can_data, csv_writer
    latest_can_data.update(parsed)

    # 로깅이 활성화되어 있고, FRAME_0 메시지를 받으면 CSV에 한 줄 기록
    if logging_active and csv_writer and arbitration_id == EMU_IDS["FRAME_0"]:
        # CSV에 기록할 데이터 행(row) 생성
        row = {"Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}
        row.update(latest_gps_data)
        row.update(latest_can_data)
        row.update(latest_acc_data)
        
        csv_writer.writerow(row)
        gpio.blink_logging_led_once(50) # 로깅 LED를 짧게 깜빡여 기록되었음을 표시

def on_gps_update(gps_parsed: dict):
    """GPS 데이터 갱신 시 호출되는 콜백. 최신 GPS 상태를 업데이트합니다."""
    global latest_gps_data
    latest_gps_data.update(gps_parsed)

def on_acc_update(acc_parsed: dict):
    """가속도계 데이터 갱신 시 호출되는 콜백. 최신 가속도계 상태를 업데이트합니다."""
    global latest_acc_data
    latest_acc_data.update(acc_parsed)

def toggle_logging(gpio: GpioController):
    """
    로깅 시작/정지 버튼을 처리하는 함수.
    - CSV 파일을 열거나 닫고, 관련 객체를 설정/해제합니다.
    - 로깅 상태 LED를 켜거나 끕니다.
    """
    global logging_active, csv_file, csv_writer
    logging_active = not logging_active

    if logging_active:
        gpio.set_logging_led(True)
        # 로그 파일 이름에 현재 시간을 포함하여 생성
        csv_filename = f"{LOG_DIR}/datalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        os.makedirs(LOG_DIR, exist_ok=True) # 로그 디렉토리가 없으면 생성
        print(f"\n버튼: 로깅 시작 → {csv_filename}")
        
        csv_file = open(csv_filename, "w", newline="", encoding='utf-8')
        
        # CSV 파일의 헤더(필드 이름) 정의
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
            "ax_g", "ay_g", "az_g" # 가속도계 데이터 필드
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
    """Ctrl+C 등 종료 신호를 받았을 때 호출되는 함수."""
    if not exit_event.is_set():
        print("\n종료 신호 수신. 안전 종료 중...", flush=True)
        exit_event.set()

def run():
    """메인 실행 함수."""
    global last_button_ts
    ensure_root()

    # --- 객체 초기화 ---
    fb = FirebaseClient()
    gpio = GpioController()

    # --- 콜백 함수에 필요한 객체 바인딩 ---
    # 각 콜백이 자신에게 필요한 객체(gpio 등)에 접근할 수 있도록 람다 함수로 감싸줍니다.
    def _can_cb(arbid, parsed): return on_can_parsed(arbid, parsed, gpio)
    def _gps_cb(parsed): return on_gps_update(parsed)
    def _acc_cb(parsed): return on_acc_update(parsed)

    # --- 워커(센서 처리) 객체 생성 ---
    canw = CanWorker(on_parsed=_can_cb)
    gpsw = GpsWorker(serial_port=SERIAL_PORT, baudrate=BAUD_RATE, on_update=_gps_cb)
    accw = AccelWorker(i2c_bus=1, address=0x53, on_update=_acc_cb)

    # --- 백그라운드 스레드 시작 ---
    wifi_thread = start_wifi_monitor(gpio, exit_event)

    # --- 워커 시작 ---
    print("CAN 인터페이스 활성화 및 버스 열기...")
    canw.start()
    
    try:
        print("GPS 포트 열기...")
        gpsw.start()
        print(f"GPS 수신 시작: {SERIAL_PORT} @ {BAUD_RATE}")
    except Exception as e:
        print(f"경고: GPS 포트 초기화 실패: {e}", file=sys.stderr)

    try:
        print("ADXL345 시작...")
        accw.start()
        print("ADXL345 준비 완료 (I²C-1, 0x53)")
    except Exception as e:
        print(f"경고: ADXL345 초기화 실패: {e}", file=sys.stderr)

    print("\n대기 중... 버튼을 눌러 로깅을 시작/정지하세요. (종료: Ctrl+C)")

    # --- 메인 루프 ---
    last_firebase_update_ts = 0.0
    last_csv_flush_ts = 0.0
    
    try:
        while not exit_event.is_set():
            now = time.time()

            # 1. 버튼 입력 처리 (300ms 디바운싱)
            if gpio.read_button_pressed() and now - last_button_ts > 0.3:
                toggle_logging(gpio)
                last_button_ts = now

            # 2. 각 센서 데이터 1회 읽기
            canw.recv_once(timeout=0.02)
            gpsw.read_once()
            accw.read_once()

            # 3. [성능 개선] 주기적인 Firebase 업데이트 (0.2초마다)
            if now - last_firebase_update_ts > 0.2:
                patch_legacy_realtime(fb)
                last_firebase_update_ts = now

            # 4. [성능 개선] 주기적인 CSV 파일 flush (0.5초마다)
            if logging_active and csv_file and now - last_csv_flush_ts > 0.5:
                csv_file.flush()
                last_csv_flush_ts = now
            
            # 루프의 과도한 CPU 점유를 막기 위한 짧은 대기
            time.sleep(0.005)

    except Exception as e:
        print(f"\n메인 루프에서 심각한 오류 발생: {e}", file=sys.stderr)
        gpio.set_error_led(True)
    finally:
        # --- 종료 처리 ---
        exit_event.set()
        
        print("모든 워커 종료 중...", flush=True)
        canw.shutdown()
        gpsw.shutdown()
        accw.shutdown()

        if wifi_thread:
            wifi_thread.join(timeout=2.0)

        if csv_file and not csv_file.closed:
            print(f"열려있는 로그 파일 저장: {csv_file.name}")
            csv_file.close()
            
        gpio.cleanup()
        print("정리 완료. 프로그램 종료.")

if __name__ == "__main__":
    # SIGINT(Ctrl+C)와 SIGTERM(종료 명령) 신호를 처리할 함수 등록
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    run()
