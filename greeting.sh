#!/bin/bash

# ===== ANSI 颜色定义 =====
RESET="\033[0m"

BOLD="\033[1m"
DIM="\033[2m"

RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
CYAN="\033[36m"

BRIGHT_YELLOW="\033[93m"
BRIGHT_BLUE="\033[94m"
BRIGHT_CYAN="\033[96m"
GRAY="\033[90m"

# ===== 获取当前小时与用户名 =====
HOUR=$(date +%H)
USERNAME=$(whoami)

# ===== 时间段英文问候 =====
if [ "$HOUR" -ge 5 ] && [ "$HOUR" -lt 12 ]; then
    GREETING_EN="Good morning"
elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 18 ]; then
    GREETING_EN="Good afternoon"
elif [ "$HOUR" -ge 18 ] && [ "$HOUR" -lt 22 ]; then
    GREETING_EN="Good evening"
else
    GREETING_EN="It's late, take care"
fi

# ===== LDAP 查询 displayName =====
LDAP_URI="ldap://192.168.102.101:389"
BASE_DN="ou=People,dc=sugon,dc=com"
DISPLAY_NAME=$(ldapsearch -x -LLL -H "$LDAP_URI" -b "$BASE_DN" "uid=$USERNAME" displayName 2>/dev/null \
    | awk '/^displayName:/ { $1=""; print substr($0,2) }')

if [ -z "$DISPLAY_NAME" ]; then
    DISPLAY_NAME=$USERNAME
fi

# ===== 英文问候列表 =====
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

# 随机选一条
RANDOM_MSG=${MESSAGES[$RANDOM % ${#MESSAGES[@]}]}

# ===== 输出 =====
echo -e "${GRAY}────────────────────────────────────────────${RESET}"

if echo "$RANDOM_MSG" | grep -q "$DISPLAY_NAME"; then
    # 已包含用户名
    echo -e "${BRIGHT_BLUE}${BOLD}LUMIA${RESET}  ${CYAN}${GREETING_EN}${RESET}, ${BRIGHT_YELLOW}${BOLD}${DISPLAY_NAME}${RESET}"
    echo -e "${DIM}${RANDOM_MSG}${RESET}"
else
    # 不包含用户名
    echo -e "${BRIGHT_BLUE}${BOLD}LUMIA${RESET}  ${CYAN}${GREETING_EN}${RESET}, ${BRIGHT_YELLOW}${BOLD}${DISPLAY_NAME}${RESET}"
    echo -e "${DIM}${RANDOM_MSG}${RESET}"
fi

echo -e "${GRAY}────────────────────────────────────────────${RESET}"