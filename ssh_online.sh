#!/usr/bin/env bash
# Show currently connected SSH users (real TCP connections):
# username, remote IP, login time
# Works on most Linux (needs: ss, ps, who, awk, grep)

set -o errexit
set -o nounset
set -o pipefail

# If ss is missing, fallback to netstat
SS_CMD=""
if command -v netstat >/dev/null 2>&1; then
  SS_CMD="netstat -tnpa 2>/dev/null | grep ESTABLISHED | grep ':22 '"
elif command -v ss >/dev/null 2>&1; then
  SS_CMD="ss -tnp 'sport = :22' state established"
else
  echo "Need 'ss' or 'netstat'." >&2
  exit 1
fi

# 获取 ESTABLISHED 的 sshd 连接行
get_established_lines() {
  # 统一输出格式：<peer_addr:peer_port>|||<pid>
  if [[ "$SS_CMD" == ss* ]]; then
    # ss 输出示例：... ESTAB ... 1.2.3.4:22  5.6.7.8:54321 users:(("sshd",pid=1234,fd=3))
    eval "$SS_CMD" 2>/dev/null | awk '
      /users:\(\("sshd"/ && /ESTAB/ {
        peer=$5
        pid=""
        if (match($0, /pid=([0-9]+)/, m)) pid=m[1]
        if (peer!="") print peer "|||" pid
      }'
  else
    # netstat 输出：tcp ... server:22   peer:54321 ESTABLISHED 1234/sshd
    eval "$SS_CMD" | awk '
      {
        peer=$5; proc=$7
        pid=""; if (match(proc, /^([0-9]+)/, m)) pid=m[1]
        if (peer!="" && pid!="") print peer "|||" pid
      }'
  fi
}

# 去掉末尾端口，适配 IPv4/IPv6
strip_port() {
  local endpoint="$1"
  # 先去掉方括号（IPv6 形如 [2001:db8::1]:54321）
  endpoint="${endpoint#[}"
  endpoint="${endpoint%]}"
  # 去掉最后一个冒号后的端口
  echo "$endpoint" | awk '{ sub(/:[0-9]+$/, "", $0); print $0 }'
}

# 从 sshd 连接进程找到会话信息（用户名、TTY、会话进程）
# 可能拿到的是 "sshd: user [priv]"，需要找子进程 "sshd: user@pts/X"
resolve_session() {
  local base_pid="$1"

  # 读某个 PID 的 cmdline（更鲁棒）
  get_cmd() {
    local pid="$1"
    # 某些系统 /proc/<pid>/cmdline 用 NUL 分隔，这里转空格
    tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true
  }

  # 从字符串中解析 "sshd: user@pts/N" 或 "sshd: user [priv]"
  parse_user_tty_from_cmd() {
    local cmd="$1"
    local user="" tty=""
    if [[ "$cmd" =~ sshd:\ ([^[:space:]]+)\@((pts|tty)/[0-9]+) ]]; then
      user="${BASH_REMATCH[1]}"
      tty="${BASH_REMATCH[2]}"
      echo "$user|||$tty"
      return 0
    elif [[ "$cmd" =~ sshd:\ ([^[:space:]]+)\ \[priv\] ]]; then
      # 仅拿到了 user，稍后去子进程找 tty
      user="${BASH_REMATCH[1]}"
      echo "$user|||"
      return 0
    fi
    echo "|||"   # 未匹配
    return 1
  }

  local cmd
  cmd="$(get_cmd "$base_pid")"
  local parsed user tty
  parsed="$(parse_user_tty_from_cmd "$cmd" || true)"
  user="${parsed%%|||*}"
  tty="${parsed##*|||}"

  # 如果没拿到 tty，找子进程中的 "sshd: user@pts/N"
  local session_pid="$base_pid"
  if [[ -z "$tty" ]]; then
    # 列出直系子进程，优先找符合的
    while IFS= read -r child; do
      [[ -z "$child" ]] && continue
      local ccmd
      ccmd="$(get_cmd "$child")"
      if [[ "$ccmd" =~ sshd:\ ([^[:space:]]+)\@((pts|tty)/[0-9]+) ]]; then
        user="${BASH_REMATCH[1]}"
        tty="${BASH_REMATCH[2]}"
        session_pid="$child"
        break
      fi
    done < <(pgrep -P "$base_pid" || true)
  fi

  echo "$user|||$tty|||$session_pid"
}

# 通过 TTY 从 who 获取登录时间；如果拿不到（如 sftp），用进程启动时间兜底
get_login_time() {
  local tty="$1" session_pid="$2"
  local t=""
  if [[ -n "$tty" ]]; then
    # who 第3/4列一般为 日期 时间
    t="$(who | awk -v T="$tty" '$2==T {print $3" "$4; exit}')"
  fi
  if [[ -z "$t" && -n "$session_pid" ]]; then
    # 兜底：用进程启动时间（更贴近“会话开始”）
    t="$(ps -o lstart= -p "$session_pid" 2>/dev/null | sed -e 's/^ *//')"
  fi
  echo "$t"
}

echo -e "USER\tREMOTE_IP\tLOGIN_TIME"

# 用关联数组避免重复 PID
declare -A seen

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  peer="${line%%|||*}"
  pid="${line##*|||}"
  [[ -z "$pid" ]] && continue
  [[ -n "${seen[$pid]:-}" ]] && continue
  seen["$pid"]=1

  remote_ip="$(strip_port "$peer")"

  session_info="$(resolve_session "$pid")"   # user|||tty|||session_pid
  user="${session_info%%|||*}"
  rest="${session_info#*|||}"
  tty="${rest%%|||*}"
  session_pid="${rest##*|||}"

  # 如果还拿不到用户名，退一步用 ps 的实际属主
  if [[ -z "$user" ]]; then
    user="$(ps -o user= -p "$pid" 2>/dev/null | awk '{print $1}')"
  fi

  login_time="$(get_login_time "$tty" "$session_pid")"

  # 清理空白
  user="${user:-unknown}"
  remote_ip="${remote_ip:-unknown}"
  login_time="${login_time:-unknown}"

  echo -e "${user}\t${remote_ip}\t${login_time}"
done < <(get_established_lines)