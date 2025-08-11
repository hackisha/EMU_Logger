!/bin/bash

for i in {1..30}; do
    if ip link show can0 > /dev/null 2>&1; then
        /sbin/ip link set can0 down
        /sbin/ip link set can0 type can bitrate 1000000
        /sbin/ip link set can0 up
        exit 0
    fi
    sleep 1
done

echo "오류: 30초 안에 can0 인터페이스가 나타나지 않음." >&2
exit 1
