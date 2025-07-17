#!/bin/env bash
# 统计 /home 下每个用户目录的大小，并按大小降序排序。
# 用法： ./home_summary.sh [并行任务数]

# 并行任务数，默认为 CPU 核心数
PARALLEL=${1:-$(nproc)}

# 如果 /home 不存在或没有子目录，直接退出
shopt -s nullglob
dirs=(/home/*)
if [ ${#dirs[@]} -eq 0 ]; then
  echo "/home 下没有任何子目录，退出"
  exit 1
fi

# 并行统计每个目录的大小，并按大小降序排序
printf '%s\0' "${dirs[@]}" | \
  xargs -0 -n1 -P"$PARALLEL" du -sh 2>/dev/null | \
  sort -hr
