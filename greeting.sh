#!/bin/bash

# 获取当前小时与用户名
HOUR=$(date +%H)
USERNAME=$(whoami)

# 时间段中英文问候
if [ "$HOUR" -ge 5 ] && [ "$HOUR" -lt 12 ]; then
    # GREETING_CN="早上好"
    GREETING_EN="Good morning"
elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 18 ]; then
    # GREETING_CN="下午好"
    GREETING_EN="Good afternoon"
elif [ "$HOUR" -ge 18 ] && [ "$HOUR" -lt 22 ]; then
    # GREETING_CN="晚上好"
    GREETING_EN="Good evening"
else
    # GREETING_CN="夜深了，注意休息"
    GREETING_EN="It's late, take care"
fi

# LDAP 查询 displayName
LDAP_URI="ldap://192.168.102.101:389"
BASE_DN="ou=People,dc=sugon,dc=com"
DISPLAY_NAME=$(ldapsearch -x -LLL -H "$LDAP_URI" -b "$BASE_DN" "uid=$USERNAME" displayName 2>/dev/null | awk '/^displayName:/ { $1=""; print substr($0,2) }')
if [ -z "$DISPLAY_NAME" ]; then
    DISPLAY_NAME=$USERNAME
fi

# 英文问候列表（部分含用户名）
MESSAGES=(
    "Welcome aboard the LUMIA cluster. Let's get productive!"
    "You're now connected to LUMIA — may the compute be with you."
    "Glad to see you, $DISPLAY_NAME. LUMIA is ready to serve."
    "Access granted. Let's make some breakthroughs today."
    "Welcome to LUMIA — where ideas meet computation."
    "May your loss converge and your clusters be meaningful."
    "Hello, $DISPLAY_NAME. May your gradients flow smoothly."
    "Welcome back, $DISPLAY_NAME. Compute time awaits."
)

# 随机选一条问候
RANDOM_MSG=${MESSAGES[$RANDOM % ${#MESSAGES[@]}]}

# 判断是否已包含用户名
if echo "$RANDOM_MSG" | grep -q "$DISPLAY_NAME"; then
    # 含有用户名，直接输出
    echo -e "$RANDOM_MSG"
else
    # 没有用户名，输出中英文时间问候 + 随机消息
    echo -e "$GREETING_EN, $DISPLAY_NAME.\n$RANDOM_MSG"
fi
