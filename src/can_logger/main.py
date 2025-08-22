# -*- coding: utf-8 -*-

import os
import sys
import csv
import signal
import time
import threading
from datetime import datetime

# 모듈 임포트
from .config import (
    LOG_DIR, SERIAL_PORT, BAUD_RATE, CAN_CHANNEL, CAN_BITRATE,
    EMU_IDS, FB_PATHS, CAN_UPLOAD_INTERVAL_SEC, GPS_UPLOAD_INTERVAL_SEC
)
from .firebase_client import FirebaseClient
from .gpio_ctl import GpioController
from .can_worker import CanWorker
from .gps_worker import GpsWorker
from .wifi_monitor import start_wifi_monitor
from .accel_worker import AccelWorker

# ======== 전역 상태 변수 ======== 
exit_event = threading.Event()
logging_active = False
last_button_press_time = 0.0

# 데이터 저장소
latest_can_data = {}
latest_gps_data = {}
latest_acc_data = {}

# CSV 로깅 관련
csv_file = None
csv_writer = None

# ======== 콜백 함수들 ======== 
def on_can_message(arbitration_id: int, parsed: dict):
    """CAN 메시지 수신 시 호출될 콜백"""
    global latest_can_data
    latest_can_data.update(parsed)

def on_gps_update(parsed: dict):
    """GPS 데이터 갱신 시 호출될 콜백"""
    global latest_gps_data
    latest_gps_data.update(parsed)

def on_accel_update(parsed: dict):
    """가속도계 데이터 갱신 시 호출될 콜백"""
    global latest_acc_data
    latest_acc_data.update(parsed)

# ======== 핵심 로직 ======== 
def toggle_logging_state(gpio: GpioController):
    """CSV 로깅 상태를 토글합니다."""
    global logging_active, csv_file, csv_writer
    logging_active = not logging_active

    if logging_active:
        gpio.set_logging_led(True)
        os.makedirs(LOG_DIR, exist_ok=True)
        filename = f"{LOG_DIR}/datalog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        print(f"\n[INFO] 로깅 시작 -> {filename}")
        
        csv_file = open(filename, 'w', newline='', encoding='utf-8')
        
        fieldnames = [
            "Timestamp", "Latitude", "Longitude", "GPS_Speed_KPH", "Satellites", "Altitude_m", "Heading_deg",
            "RPM","TPS_percent","IAT_C","MAP_kPa","PulseWidth_ms","AnalogIn1_V","AnalogIn2_V","AnalogIn3_V","AnalogIn4_V",
            "VSS_kmh","Baro_kPa","OilTemp_C","OilPressure_bar","FuelPressure_bar","CLT_C","IgnAngle_deg","DwellTime_ms",
            "WBO_Lambda","LambdaCorrection_percent","EGT1_C","EGT2_C","Gear","EmuTemp_C","Batt_V","CEL_Error","Flags1",
            "Ethanol_percent","DBW_Pos_percent","DBW_Target_percent","TC_drpm_raw","TC_drpm","TC_TorqueReduction_percent",
            "PitLimit_TorqueReduction_percent","AnalogIn5_V","AnalogIn6_V","OutFlags1","OutFlags2","OutFlags3","OutFlags4",
            "BoostTarget_kPa","PWM1_DC_percent","DSG_Mode","LambdaTarget","PWM2_DC_percent","FuelUsed_L",
            "ax_g", "ay_g", "az_g"
        ]
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction='ignore')
        csv_writer.writeheader()
    else:
        print("\n[INFO] 로깅 중지.")
        gpio.set_logging_led(False)
        if csv_file:
            name = csv_file.name
            csv_file.close()
            print(f"[INFO] 로그 파일 저장 완료: {name}")
        csv_file = None
        csv_writer = None

def write_csv_log_entry(gpio: GpioController):
    """결합된 데이터로 CSV 파일에 한 줄을 기록합니다."""
    if not logging_active or not csv_writer:
        return

    full_row = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "Latitude": latest_gps_data.get("lat"), "Longitude": latest_gps_data.get("lon"),
        "GPS_Speed_KPH": latest_gps_data.get("GPS_Speed_KPH"), "Satellites": latest_gps_data.get("satellites"),
        "Altitude_m": latest_gps_data.get("altitude"), "Heading_deg": latest_gps_data.get("heading"),
    }
    full_row.update(latest_can_data)
    full_row.update(latest_acc_data)
    
    csv_writer.writerow(full_row)
    gpio.blink_logging_led_once(duration_ms=50)

def print_status_line():
    """터미널에 현재 상태를 한 줄로 출력합니다."""
    gps_status = "OK" if latest_gps_data.get("gps_fix") else "No Fix"
    vss = latest_can_data.get('VSS_kmh', latest_gps_data.get('GPS_Speed_KPH', 0.0))
    status_text = (
        "RPM:{:>5} | MAP:{:>3}kPa | TPS:{:>5.1f}% | Batt:{:>4.1f}V | "
        "CLT:{:>4}°C | VSS:{:>5.1f}km/h | GPS:{} | Logging: {}"
    ).format(
        latest_can_data.get('RPM', 0), latest_can_data.get('MAP_kPa', 0),
        latest_can_data.get('TPS_percent', 0.0), latest_can_data.get('Batt_V', 0.0),
        latest_can_data.get('CLT_C', 0), vss, gps_status, "ON" if logging_active else "OFF"
    )
    sys.stdout.write("\r" + status_text + "   ")

def can_firebase_uploader(fb: FirebaseClient, stop_event: threading.Event):
    """주기적으로 CAN + 가속도계 데이터를 Firebase에 업로드"""
    while not stop_event.is_set():
        data_to_upload = {}
        data_to_upload.update(latest_can_data)
        data_to_upload.update(latest_acc_data)

        if data_to_upload:
            data_to_upload['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            if 'VSS_kmh' not in data_to_upload and 'GPS_Speed_KPH' in latest_gps_data:
                data_to_upload['VSS_kmh'] = latest_gps_data.get('GPS_Speed_KPH', 0.0)
            fb.patch(FB_PATHS["LEGACY_REALTIME"], data_to_upload)
        
        stop_event.wait(CAN_UPLOAD_INTERVAL_SEC)

def gps_firebase_uploader(fb: FirebaseClient, stop_event: threading.Event):
    """주기적으로 GPS 데이터를 Firebase에 업로드"""
    while not stop_event.is_set():
        if latest_gps_data:
            data_to_upload = latest_gps_data.copy()
            data_to_upload['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            fb.patch(FB_PATHS["LEGACY_REALTIME"], data_to_upload)

        stop_event.wait(GPS_UPLOAD_INTERVAL_SEC)

def handle_exit(signum, frame):
    print("\n[INFO] 종료 신호 수신. 리소스를 정리합니다...")
    exit_event.set()

def worker_loop(worker, stop_event: threading.Event):
    """Worker의 read/recv_once를 루프에서 계속 호출하는 스레드 대상 함수"""
    # getattr을 사용하여 유연하게 메소드 호출
    method_name = "recv_once" if hasattr(worker, "recv_once") else "read_once"
    read_method = getattr(worker, method_name)
    
    while not stop_event.is_set():
        try:
            read_method()
        except Exception as e:
            print(f"\n[ERROR] {type(worker).__name__} 스레드에서 오류 발생: {e}", file=sys.stderr)
            # 심각한 오류 시 스레드 종료 (예: CAN 버스 다운)
            if isinstance(e, (IOError, OSError)):
                break
        # CPU 과점 방지를 위한 짧은 대기
        time.sleep(0.001)

def main():
    """메인 실행 함수"""
    global last_button_press_time
    
    if os.geteuid() != 0:
        print("오류: 이 스크립트는 sudo 권한으로 실행해야 합니다.")
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # --- 초기화 ---
    gpio = GpioController()
    fb = FirebaseClient()
    can_worker = CanWorker(on_message=on_can_message)
    gps_worker = GpsWorker(port=SERIAL_PORT, baudrate=BAUD_RATE, on_update=on_gps_update)
    accel_worker = AccelWorker(on_update=on_accel_update)
    
    # --- Worker 시작 ---
    try:
        can_worker.start()
        gps_worker.start()
    except Exception as e:
        print(f"[ERROR] 필수 Worker(CAN/GPS) 시작 실패: {e}", file=sys.stderr)
        gpio.set_error_led(True)
        exit_event.set()

    try:
        accel_worker.start()
        print("가속도계(ADXL345) 시작 완료.")
    except Exception as e:
        print(f"[WARNING] 가속도계 시작 실패: {e}. 가속도 데이터 없이 계속합니다.", file=sys.stderr)

    # --- 스레드 시작 ---
    start_wifi_monitor(gpio, exit_event)
    
    can_fb_thread = threading.Thread(target=can_firebase_uploader, args=(fb, exit_event), daemon=True)
    gps_fb_thread = threading.Thread(target=gps_firebase_uploader, args=(fb, exit_event), daemon=True)
    
    # 데이터 수집 워커 스레드
    can_thread = threading.Thread(target=worker_loop, args=(can_worker, exit_event), daemon=True)
    gps_thread = threading.Thread(target=worker_loop, args=(gps_worker, exit_event), daemon=True)
    accel_thread = threading.Thread(target=worker_loop, args=(accel_worker, exit_event), daemon=True)

    can_fb_thread.start()
    gps_fb_thread.start()
    print("Firebase 업로드 스레드 시작 (CAN/ACC: 0.2s, GPS: 1.0s)")
    
    can_thread.start()
    gps_thread.start()
    accel_thread.start()
    print("데이터 수집 스레드 시작 (CAN, GPS, ACCEL)")

    if not exit_event.is_set():
        print("\n[INFO] 데이터 수집을 시작합니다. 버튼을 눌러 로깅을 제어하세요. (종료: Ctrl+C)")

    # --- 메인 루프 ---
    last_csv_write_time = 0.0
    try:
        while not exit_event.is_set():
            now = time.time()
            # 1. 버튼 입력 처리 (Debounce 포함)
            if gpio.read_button_pressed() and (now - last_button_press_time > 0.3):
                last_button_press_time = now
                toggle_logging_state(gpio)
            
            # 2. CSV 로깅 (20Hz, 50ms 간격)
            if logging_active and (now - last_csv_write_time > 0.05):
                write_csv_log_entry(gpio)
                last_csv_write_time = now

            # 3. 상태 출력
            print_status_line()
            
            # 메인 루프는 CPU를 많이 사용하지 않도록 잠시 대기
            time.sleep(0.05)

    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"\n[FATAL] 메인 루프에서 심각한 오류 발생: {e}", file=sys.stderr)
        gpio.set_error_led(True)
    finally:
        exit_event.set()
        print("\n[INFO] 모든 스레드와 Worker를 종료합니다.")
        
        # 스레드가 정상적으로 종료될 시간을 잠시 줌
        can_thread.join(timeout=0.5)
        gps_thread.join(timeout=0.5)
        accel_thread.join(timeout=0.5)
        can_fb_thread.join(timeout=0.5)
        gps_fb_thread.join(timeout=0.5)

        can_worker.shutdown()
        gps_worker.shutdown()
        accel_worker.shutdown()
        
        if csv_file and not csv_file.closed:
            csv_file.close()
            print(f"[INFO] 로그 파일 저장 완료: {csv_file.name}")
        
        gpio.cleanup()
        print("[INFO] 프로그램이 완전히 종료되었습니다.")

if __name__ == "__main__":
    main()
