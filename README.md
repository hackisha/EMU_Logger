# EMU_Logger

## Getting Start

Run the logger as a module from the `src` directory:

```bash
cd src
python -m can_logger.main
```

EMU Black Data Logger for MF-25
## PCB
<img width="1377" height="798" alt="image" src="https://github.com/user-attachments/assets/f7d34a73-1d54-47b3-990c-a37b06438d0c" />

---

<img width="1407" height="464" alt="image" src="https://github.com/user-attachments/assets/597415f6-2983-469c-8f1b-2ad00ea69bce" />

## WIFI
```
# 1) 프로파일 생성
nmcli connection add type wifi ifname wlan0 con-name SSID1 ssid "SSID1"
nmcli connection add type wifi ifname wlan0 con-name SSID2 ssid "SSID2"
nmcli connection add type wifi ifname wlan0 con-name SSID3 ssid "SSID3"

# 2) 보안/비밀번호 설정 (WPA/WPA2-Personal)
nmcli connection modify SSID1 wifi-sec.key-mgmt wpa-psk wifi-sec.psk "비밀번호1"
nmcli connection modify SSID2 wifi-sec.key-mgmt wpa-psk wifi-sec.psk "비밀번호2"
nmcli connection modify SSID3 wifi-sec.key-mgmt wpa-psk wifi-sec.psk "비밀번호3"

# 3) 자동 연결/우선순위(클수록 우선)
nmcli connection modify SSID1 connection.autoconnect yes connection.autoconnect-priority 20
nmcli connection modify SSID2 connection.autoconnect yes connection.autoconnect-priority 10
nmcli connection modify SSID3 connection.autoconnect yes connection.autoconnect-priority 5

# 4) 즉시 연결 테스트
nmcli connection up SSID1
```

## systemctl
```
sudo nano /etc/systemd/system/can-logger.service
```
```
[Unit]
Description=CAN Logger Service for EMU Black
After=network-online.target

[Service]
User=root
WorkingDirectory=/home/pi/your_project_directory
ExecStart=/usr/bin/python3 -m can_logger.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```
sudo systemctl daemon-reload
sudo systemctl enable can-logger.service
sudo systemctl start can-logger.service
```
