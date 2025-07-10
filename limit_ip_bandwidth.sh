#!/bin/bash

# 用法: ./limit_upload.sh <ip1> [ip2] ...
if [ $# -lt 1 ]; then
    echo "用法: $0 <ip1> [ip2] ..."
    exit 1
fi

DEV="ens8f0"
IPS=("$@")
RATE="80mbit"   # 上传限速 = 10MB/s
MAX_PARENT_RATE="10gbit"

# 如果 qdisc 不存在则添加
if ! tc qdisc show dev "$DEV" | grep -q 'htb 1:'; then
    echo "初始化上传限速 qdisc..."
    tc qdisc add dev "$DEV" root handle 1: htb default 999
    tc class add dev "$DEV" parent 1: classid 1:1 htb rate $MAX_PARENT_RATE
fi

# 获取当前最大 classid 编号
USED_IDS=$(tc class show dev "$DEV" | grep -oE 'classid 1:[0-9a-f]+' | cut -d: -f2)
MAX_ID=10
for ID in $USED_IDS; do
    DEC=$((16#$ID))
    if [ $DEC -ge $MAX_ID ]; then
        MAX_ID=$((DEC + 10))
    fi
done

# 添加每个 IP 的上传限速规则
for IP in "${IPS[@]}"; do
    CLASS_HEX=$(printf "%x" $MAX_ID)

    echo "添加上传限速：$IP => $RATE (classid=1:$CLASS_HEX)"
    tc class add dev "$DEV" parent 1:1 classid 1:$CLASS_HEX htb rate $RATE ceil $RATE
    tc filter add dev "$DEV" protocol ip parent 1:0 prio 1 u32 match ip dst "$IP" flowid 1:$CLASS_HEX

    ((MAX_ID+=10))
done

echo "所有上传限速规则添加完成。"
