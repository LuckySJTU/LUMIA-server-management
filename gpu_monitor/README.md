# GPU Monitor

`gpu_monitor` 是一个按 [READMEv1.md](/home/yxwang/LUMIA-server-management/gpu_monitor/READMEv1.md) 一期规划落地的 Slurm GPU 资源监控实现，分为两部分：

- 计算节点：`gpu_monitor.node_agent`
- 汇总节点：`gpu_monitor.controller_app`

当前版本不提供前端页面，只提供完整的采集、缓存、上报、聚合、告警和查询 API。

## 目录说明

- [gpu_monitor/node_agent.py](/home/yxwang/LUMIA-server-management/gpu_monitor/node_agent.py)：计算节点常驻 agent + Slurm hook 入口
- [gpu_monitor/controller_app.py](/home/yxwang/LUMIA-server-management/gpu_monitor/controller_app.py)：汇总节点 API 与后台 worker
- [gpu_monitor/shared.py](/home/yxwang/LUMIA-server-management/gpu_monitor/shared.py)：公共配置
- [gpu_monitor/slurm_prolog.sh](/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_prolog.sh)：Slurm Prolog 脚本
- [gpu_monitor/slurm_epilog.sh](/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_epilog.sh)：Slurm Epilog 脚本
- [gpu_monitor/slurm_task_prolog.sh](/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_prolog.sh)：Slurm TaskProlog 脚本
- [gpu_monitor/slurm_task_epilog.sh](/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_epilog.sh)：Slurm TaskEpilog 脚本
- [gpu_monitor/requirements.txt](/home/yxwang/LUMIA-server-management/gpu_monitor/requirements.txt)：Python 依赖

## Python 版本

推荐使用：

- Python `3.10.x` 或 `3.11.x`

当前代码已按 Python `3.10.20` 兼容处理。之前启动报错的原因是旧版本代码使用了 `datetime.UTC`，该常量只在 Python `3.11+` 中存在；现已改为 `timezone.utc`。

## 一期能力

- 基于 `Prolog/Epilog` + `TaskProlog/TaskEpilog` + shell fallback + 节点 agent 事件消费维护 job-user-node-gpu 映射
- 节点端每 15 秒采集活跃 GPU 的 `gpu_util_percent` / `mem_used_bytes` / `mem_total_bytes` / `mem_util_percent`
- 节点端用 SQLite WAL 做本地缓存，控制节点不可达时保留最近 2 小时未送达样本
  - 当前默认已调整为保留最近 24 小时未送达样本
- 节点端每 1 分钟批量上报 `/api/v1/ingest/metrics`
- 控制节点提供以下 API：
  - `POST /api/v1/ingest/metrics`
  - `POST /api/v1/ingest/heartbeat`
  - `GET /api/v1/overview/realtime`
  - `GET /api/v1/overview/history`
  - `GET /api/v1/jobs`
  - `GET /api/v1/jobs/{job_id}`
  - `GET /api/v1/users`
  - `GET /api/v1/users/{user_name}`
  - `GET /api/v1/nodes`
  - `GET /api/v1/nodes/{node_name}`
  - `GET /api/v1/alerts`
- 控制节点后台 worker：
  - 小时聚合
  - retention 清理
  - 低利用率告警扫描

## 部署方式

### 1. 安装依赖

建议在汇总节点和计算节点都创建同一个 Python 虚拟环境：

```bash
cd /home/yxwang/LUMIA-server-management
python3 -m venv .venv
source .venv/bin/activate
pip install -r gpu_monitor/requirements.txt
```

## 汇总节点部署

### 1. 配置环境变量

汇总节点现在按 PostgreSQL 部署，数据库用户和库需要提前创建好。最少需要：

```bash
export PYTHONPATH=/home/yxwang/LUMIA-server-management
export GPU_MONITOR_DATABASE_URL="postgresql+psycopg://gpu_monitor:password@127.0.0.1:5432/gpu_monitor"
export GPU_MONITOR_API_HOST="0.0.0.0"
export GPU_MONITOR_API_PORT="8001"
export GPU_MONITOR_CLUSTER_NAME="lumia"
export GPU_MONITOR_ENABLE_EMBEDDED_WORKER="false"
export GPU_MONITOR_DB_POOL_SIZE="20"
export GPU_MONITOR_DB_MAX_OVERFLOW="40"
export GPU_MONITOR_DB_POOL_TIMEOUT_SECONDS="30"
export GPU_MONITOR_DB_POOL_RECYCLE_SECONDS="1800"
export GPU_MONITOR_SLURM_RECONCILE_ENABLED="true"
export GPU_MONITOR_SLURM_RECONCILE_INTERVAL_SECONDS="300"
export GPU_MONITOR_SLURM_ACTIVE_JOBS_COMMAND="squeue -h -o %A"
export GPU_MONITOR_SLURM_COMMAND_TIMEOUT_SECONDS="15"
```

说明：

- `gpu_monitor.controller_app` 现在支持 `run-api` 和 `run-worker` 两种启动模式
- 若只做本地开发，仍可把 `GPU_MONITOR_DATABASE_URL` 设回 SQLite；下面的 systemd 方案按 PostgreSQL 给出
- `GPU_MONITOR_ENABLE_EMBEDDED_WORKER=false` 用于关闭 API 进程里的内置 worker，避免和独立 worker 服务重复执行聚合与告警扫描
- `GPU_MONITOR_DB_POOL_*` 用于调节 PostgreSQL 连接池；在多节点同时批量上报时可以适当调大
- `GPU_MONITOR_SLURM_RECONCILE_*` 用于控制汇总节点的低频 Slurm 对账：如果某个 job 已不在 Slurm 活跃列表里，但控制端还没收到 `CLOSED`，worker 会把它补关并在同一轮告警扫描里解析掉对应 active alerts

### 2. 启动 API

```bash
cd /home/yxwang/LUMIA-server-management
source .venv/bin/activate
python3 -m gpu_monitor.controller_app run-api
```

### 3. 启动 worker

```bash
cd /home/yxwang/LUMIA-server-management
source .venv/bin/activate
python3 -m gpu_monitor.controller_app run-worker
```

默认监听：

- `http://127.0.0.1:8001`

本地访问示例：

```bash
curl http://127.0.0.1:8001/api/v1/overview/realtime
curl http://127.0.0.1:8001/api/v1/jobs?range=1d
curl http://127.0.0.1:8001/api/v1/alerts
```

### 4. systemd 示例

仓库里已提供：

- [gpu-monitor-api.service](/home/yxwang/LUMIA-server-management/gpu_monitor/systemd/gpu-monitor-api.service)
- [gpu-monitor-worker.service](/home/yxwang/LUMIA-server-management/gpu_monitor/systemd/gpu-monitor-worker.service)
- [controller.env.example](/home/yxwang/LUMIA-server-management/gpu_monitor/systemd/controller.env.example)

启用方式：

```bash
mkdir -p /etc/gpu-monitor
cp /home/yxwang/LUMIA-server-management/gpu_monitor/systemd/controller.env.example /etc/gpu-monitor/controller.env
$EDITOR /etc/gpu-monitor/controller.env

cp /home/yxwang/LUMIA-server-management/gpu_monitor/systemd/gpu-monitor-api.service /etc/systemd/system/
cp /home/yxwang/LUMIA-server-management/gpu_monitor/systemd/gpu-monitor-worker.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now gpu-monitor-api.service gpu-monitor-worker.service
```

## 计算节点部署

### 1. 配置环境变量

agent 侧仍然继续使用本地 SQLite，这是当前设计里用于断点续传和本地状态恢复的缓存层。最少需要：

```bash
export PYTHONPATH=/home/yxwang/LUMIA-server-management
export GPU_MONITOR_CLUSTER_NAME="lumia"
export GPU_MONITOR_NODE_NAME="$(hostname -s)"
export GPU_MONITOR_NODE_DB="/var/lib/gpu-monitor/node-agent.db"
export GPU_MONITOR_TASK_EVENT_DIR="/var/lib/gpu-monitor/events"
export GPU_MONITOR_API_BASE_URL="http://<汇总节点IP>:8001"
export GPU_MONITOR_SAMPLE_INTERVAL_SECONDS="15"
export GPU_MONITOR_FLUSH_INTERVAL_SECONDS="60"
export GPU_MONITOR_HEARTBEAT_INTERVAL_SECONDS="300"
export GPU_MONITOR_MAPPING_STALE_MINUTES="10"
export GPU_MONITOR_UNDELIVERED_RETENTION_HOURS="24"
export GPU_MONITOR_UNDELIVERED_MAX_RECORDS="100000"
export GPU_MONITOR_NODE_SLURM_RECONCILE_ENABLED="true"
export GPU_MONITOR_NODE_SLURM_RECONCILE_INTERVAL_SECONDS="300"
export GPU_MONITOR_NODE_SLURM_ACTIVE_JOBS_COMMAND="squeue -h -w {node_name} -o %A"
export GPU_MONITOR_NODE_SLURM_COMMAND_TIMEOUT_SECONDS="15"
```

说明：

- `GPU_MONITOR_NODE_DB` 是计算节点本地 SQLite 缓存文件，继续保留即可
- `GPU_MONITOR_TASK_EVENT_DIR` 用于存放 Slurm hook 写入的事件文件，建议使用持久目录而不是默认 `/tmp`
- Slurm hook 进程和 `gpu-monitor-agent` 必须看到同一个 `GPU_MONITOR_TASK_EVENT_DIR`；如果 agent 走 systemd 且启用了 `PrivateTmp=true`，就不能再依赖默认 `/tmp`
- `GPU_MONITOR_MAPPING_STALE_MINUTES` 用于兜底清理异常残留映射
- `GPU_MONITOR_NODE_SLURM_RECONCILE_*` 用于控制计算节点低频 Slurm 对账；当本地仍有 RUNNING mapping，但该 job 已不在本节点的 Slurm 活跃列表中时，会先本地补关，再补写一个可重试的 `CLOSED` 事件同步控制端
- 正常运行中的任务会在每轮采样时自动刷新 `last_seen_time`
- 如果 agent 挂掉、任务异常结束或事件丢失，超过该时间的映射会被自动标记为 `CLOSED`，并补写一个可重试的 close 事件用于同步控制节点
- `GPU_MONITOR_UNDELIVERED_RETENTION_HOURS` 控制控制节点不可达时，本地未上报样本的最长保留时间
- `GPU_MONITOR_UNDELIVERED_MAX_RECORDS` 控制本地未上报队列的上限

重启影响说明：

- `gpu-monitor-api` / `gpu-monitor-worker` 重启：分钟数据、小时聚合和告警都在 PostgreSQL 中，短时重启不会丢历史数据；计算节点会继续把样本缓存在本地 SQLite，API 恢复后再补传
- `gpu-monitor-agent` 重启：本地 `active_mappings` 和 `sample_queue` 都在 SQLite 中，重启后会继续恢复；当前实现会先处理 task 事件，再做一次低频 Slurm 对账，然后尝试采样，最后再做 stale 清理，尽量避免把仍在运行的长任务误判为 `CLOSED`
- 只有当控制节点持续不可达时间超过 `GPU_MONITOR_UNDELIVERED_RETENTION_HOURS`，或未送达样本数超过 `GPU_MONITOR_UNDELIVERED_MAX_RECORDS` 时，才会开始丢弃最旧的未送达数据

### 2. 启动节点 agent

```bash
cd /home/yxwang/LUMIA-server-management
source .venv/bin/activate
python3 -m gpu_monitor.node_agent run-agent
```

### 3. systemd 示例

仓库里已提供：

- [gpu-monitor-agent.service](/home/yxwang/LUMIA-server-management/gpu_monitor/systemd/gpu-monitor-agent.service)
- [agent.env.example](/home/yxwang/LUMIA-server-management/gpu_monitor/systemd/agent.env.example)

启用方式：

```bash
mkdir -p /etc/gpu-monitor /var/lib/gpu-monitor
cp /home/yxwang/LUMIA-server-management/gpu_monitor/systemd/agent.env.example /etc/gpu-monitor/agent.env
$EDITOR /etc/gpu-monitor/agent.env

cp /home/yxwang/LUMIA-server-management/gpu_monitor/systemd/gpu-monitor-agent.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable --now gpu-monitor-agent.service
```

## Slurm 接入

### 1. 设置 Prolog / Epilog

给脚本执行权限：

```bash
chmod +x /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_prolog.sh
chmod +x /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_epilog.sh
chmod +x /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_prolog.sh
chmod +x /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_epilog.sh
chmod +x /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_shell_register.sh
```

在 `slurm.conf` 中配置：

```ini
Prolog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_prolog.sh
Epilog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_epilog.sh
TaskProlog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_prolog.sh
TaskEpilog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_epilog.sh
PrologFlags=Alloc
```

然后重载 Slurm：

```bash
scontrol reconfigure
```

如果 Slurm 的执行环境不会自动继承你 conda/venv 里的解释器，建议显式设置：

```bash
export GPU_MONITOR_PYTHON="/home/yxwang/miniconda3/envs/gpumonitor_v1/bin/python3"
```

说明：

- `PYTHONPATH` 用于让解释器找到项目源码，应该指向 `/home/yxwang/LUMIA-server-management`
- `GPU_MONITOR_PYTHON` 用于指定实际执行的 Python 解释器
- 当前 `slurm_prolog.sh` / `slurm_epilog.sh` 会优先使用 `GPU_MONITOR_PYTHON`

### 2. hook 的行为

- `Prolog/Epilog` 负责 allocation 级别事件，用于支持 `sbatch` / `salloc` 这类资源分配场景
- `TaskProlog/TaskEpilog` 负责 `sbatch` / `srun` 这类 task 级别事件
- `Prolog` 调用 `${GPU_MONITOR_PYTHON:-python3} -m gpu_monitor.node_agent emit-alloc-register-event`
- `Epilog` 调用 `${GPU_MONITOR_PYTHON:-python3} -m gpu_monitor.node_agent emit-alloc-finish-event`
- 这些 hook 会优先读取 `/etc/gpu-monitor/agent.env`，并默认把事件写到 `/var/lib/gpu-monitor/events`
- 节点 agent 消费这些事件后，会调用控制节点 `/api/v1/ingest/job-state` 同步作业 `RUNNING/CLOSED` 状态；如果某个映射是被 stale 清理兜底关闭，agent 也会补写一个 `CLOSED` 事件并按同样链路重试同步

脚本会读取：

- `SLURM_JOB_ID`
- `SLURM_STEP_ID`
- `SLURM_JOB_USER`
- `SLURM_JOB_UID`
- `SLURM_JOB_GPUS`
- `SLURM_STEP_GPUS`
- `CUDA_VISIBLE_DEVICES`

内部统一把 `gpu_index` 转换成 `gpu_uuid` 存储。

关于 `salloc` 支持：

- 纯 `salloc` 只建立 allocation，不一定马上触发 task 级 hook
- 为了捕获这类“已占用但未启动 task”的 GPU 资源，建议启用 `PrologFlags=Alloc`
- 当前实现里，`Prolog/Epilog` 负责 allocation 级事件；`TaskProlog/TaskEpilog` 负责 task 级事件；shell fallback 只兜底纯 `salloc` 顶层 shell
- 如果某个 job 先留下了 `allocation_register` 或 `shell_register` 这类非 task 占位映射，后续同一 `job_id` 下出现真实 task 注册时，agent 会优先把这些非 task 映射补关，只保留 `task_register`
- 如果 `register_alloc` 事件晚于 `task_register` 才被 agent 处理，会被直接忽略，不再把 allocation 占位重新打回 `RUNNING`
- 如果 `Prolog` 环境拿不到 GPU 编号，可以使用用户 shell 兜底上报
- 若 `TaskProlog/TaskEpilog` 是按普通作业用户执行，则 `GPU_MONITOR_TASK_EVENT_DIR` 需要对作业用户可写；systemd 示例里已把 `/var/lib/gpu-monitor/events` 设为 `1777`

用户 shell 兜底方式：

```bash
source /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_shell_register.sh
```

这个脚本会：

- 检查当前是否处于 Slurm 作业环境
- 只在交互式、且没有 task 级特征、且当前 job 还没有 task step marker 的顶层 allocation shell 中执行，用于 `salloc` 兜底
- 调用 `/usr/local/bin/get_real_gpu_id` 生成 `SLURM_REAL_GPUS`
- 通过 `emit-shell-register-event` 把当前 shell 的真实 GPU 分配上报给节点 agent
- 使用 `GPU_MONITOR_SHELL_REGISTERED=1` 防止同一个 shell 重复上报

如果希望在 `salloc` 进入交互 shell 后自动上报，可以在用户的 `~/.bashrc` 或 `~/.zshrc` 中加入：

```bash
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    source /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_shell_register.sh
fi
```

```zsh
if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    source /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_shell_register.zsh
fi
```

其中 `zsh` 版本会额外定义一个可手动重试的命令：

- `gpu_monitor_shell_register`

如果希望对所有普通用户生效，而不是逐个修改用户家目录，建议做系统级 shell 集成。

`bash` 推荐方式：

创建 `/etc/profile.d/gpu-monitor-shell-register.sh`：

```bash
case $- in
    *i*)
        if [[ "${EUID:-$(id -u)}" -ne 0 ]] && [[ -n "${SLURM_JOB_ID:-}" ]]; then
            source /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_shell_register.sh
        fi
        ;;
esac
```

`zsh` 推荐方式：

创建 `/etc/zsh/zprofile` 或在现有 `/etc/zsh/zprofile` 中加入：

```zsh
if [[ -o interactive ]]; then
    if [[ "${EUID:-$(id -u)}" -ne 0 ]] && [[ -n "${SLURM_JOB_ID:-}" ]]; then
        source /home/yxwang/LUMIA-server-management/gpu_monitor/slurm_shell_register.zsh
    fi
fi
```

说明：

- 只对普通用户生效，不对 `root` 生效
- 只在 Slurm 作业环境中执行
- 只在交互 shell 中执行，避免影响非交互命令
- 由于 `slurm_shell_register.sh` 会在检测到 `SLURM_STEP_ID` 时自动跳过，因此不会与 `sbatch` / `srun` 已存在的 allocation / step 注册链路冲突
- `bash` 用户通常走 `/etc/profile.d/*.sh`
- `zsh` 用户通常走 `/etc/zsh/zprofile`
- 不建议让 `zsh` 直接 `source slurm_shell_register.sh`，因为那个文件按 bash 语法实现，`zsh` 应使用 `slurm_shell_register.zsh`

在启用 `task/cgroup` 的集群上，推荐优先使用真实 GPU 编号：

- `SLURM_REAL_GPUS`

如果计算节点已经提供 `/usr/local/bin/get_real_gpu_id`，`node_agent.py` 和 `slurm_shell_register.sh` 都会优先尝试使用它解析真实 GPU 编号并导出 `SLURM_REAL_GPUS`。

随后才会回退到：

- `CUDA_VISIBLE_DEVICES`
- `GPU_DEVICE_ORDINAL`

只有这两个变量不存在时，才回退到：

- `SLURM_STEP_GPUS`
- `SLURM_JOB_GPUS`

原因是 `SLURM_STEP_GPUS` 往往表示宿主机物理 GPU 编号，而 `task/cgroup` 场景下作业内可见 GPU 会被重映射；直接把 `SLURM_STEP_GPUS` 当成当前进程 NVML index 使用会映射错卡。你提供的 `/etc/gpu_pcie_map` 和 `/usr/local/bin/get_real_gpu_id` 正好可以解决这个问题。

当前实现里的字段语义是：

- `gpu_uuid`：任务环境中实际可见并被分配到的那张卡的真实 UUID
- `gpu_index`：节点上的真实物理 GPU id，例如 `SLURM_REAL_GPUS=3` 中的 `3`
- `job_meta.node_list`：该 `job_id + step_id` 在分钟表中实际出现过的节点去重列表
- `job_meta.gpu_count`：该 `job_id + step_id` 在分钟表中实际出现过的 GPU UUID 去重数

因此在 `task/cgroup` 模式下，可能出现：

- 任务内 `nvidia-smi -L` 显示 `GPU 0`
- API 返回 `gpu_index=3`

这表示“任务里可见编号 0 对应节点物理编号 3”，是预期行为。

## API 说明

### 写入接口

#### `POST /api/v1/ingest/metrics`

请求体示例：

```json
{
  "node_name": "gpu001",
  "batch_time": "2026-03-13T12:00:00+00:00",
  "samples": [
    {
      "ts": "2026-03-13T11:59:00+00:00",
      "cluster_name": "lumia",
      "node_name": "gpu001",
      "job_id": "123456",
      "step_id": "batch",
      "user_name": "alice",
      "uid": 1001,
      "gpu_uuid": "GPU-xxxx",
      "gpu_index": 0,
      "gpu_util_percent": 82.0,
      "mem_used_bytes": 17179869184,
      "mem_total_bytes": 25769803776,
      "mem_util_percent": 66.67
    }
  ]
}
```

#### `POST /api/v1/ingest/heartbeat`

请求体示例：

```json
{
  "node_name": "gpu001",
  "agent_version": "1.0.0",
  "ts": "2026-03-13T12:00:00+00:00",
  "active_job_count": 3,
  "active_gpu_count": 6
}
```

### 查询接口

- `GET /api/v1/overview/realtime`
- `GET /api/v1/overview/history?range=7d|30d`
- `GET /api/v1/jobs?range=realtime|1d|1w`
- `GET /api/v1/jobs/{job_id}?range=1d|1w`
- `GET /api/v1/users?range=realtime|1d|1w`
- `GET /api/v1/users/{user_name}?range=1d|1w`
- `GET /api/v1/nodes?range=realtime|1d|1w`
- `GET /api/v1/nodes/{node_name}?range=1d|1w`
- `GET /api/v1/alerts?status=active|resolved&entity_type=job|user|node`

## 告警规则

当前已实现：

- 任务最近 30 分钟平均 `gpu_util_percent < 10`：`warning`
- 任务最近 2 小时平均 `gpu_util_percent < 5`：`critical`
- 最近 30 分钟显存平均利用率 `> 60` 且 GPU 平均利用率 `< 10`：`warning`
- 用户最近 1 小时占用 GPU 数 `>= 4` 且平均 GPU 利用率 `< 15`：`warning`
- 节点最近 1 小时存在至少 2 张低利用率活跃 GPU：`warning`

规则计算说明：

- 时间窗口按分钟桶跨度判断，不按样本条数判断
- 多卡任务在同一分钟可能产生多条样本，但只计作 1 个分钟桶
- 平均利用率也按“每分钟先聚合，再对分钟窗口求平均”的方式计算
- 即使中间偶尔丢了少量分钟样本，只要窗口跨度达到 30 分钟 / 1 小时 / 2 小时，仍可参与对应告警判断

## 实现说明与边界

- 节点采集依赖 `pynvml`，底层调用 NVML
- 生产部署建议控制节点使用 PostgreSQL；本地开发仍可通过 `GPU_MONITOR_DATABASE_URL` 切回 SQLite
- 小时聚合与告警扫描既可作为 API 进程内嵌 worker 运行，也可通过 `run-worker` 单独部署成 systemd 服务
- 一期未覆盖 MIG、MPS、多任务共享同一张 GPU 的精细归因
- `SLURM_JOB_GPUS` 默认按 `0,1,2` 这样的物理 GPU index 解析；如果集群里变量格式不同，需要按实际 Slurm 输出格式调整 `build_mapping_from_env`

实时总览口径说明：

- `GET /api/v1/overview/realtime` 只统计控制节点当前标记为 `RUNNING` 的作业
- 该接口会在最近 15 分钟窗口内，为每个 `job_id + step_id + node_name + gpu_uuid` 只取最新一条样本作为当前快照
- `allocated_gpu_count`、`avg_gpu_util_percent`、`avg_mem_util_percent`、`low_util_job_count` 都基于这个当前快照计算
- worker 会每 5 分钟把这一组 realtime 指标固化到 `overview_snapshot`
- `GET /api/v1/overview/history` 返回最近 `7d` 或 `30d` 的 5 分钟快照序列，字段与 `overview/realtime` 保持一致

## 验证建议

### 1. 验证汇总节点

```bash
curl http://127.0.0.1:8001/api/v1/overview/realtime
curl http://127.0.0.1:8001/api/v1/overview/history?range=7d
```

### 1.1 调试单个任务的实时统计状态

如果发现任务在计算节点已经 `CLOSED`，但控制节点实时总览仍把它算作 `running_job_count`，可以调用调试接口：

```bash
curl http://127.0.0.1:8001/api/v1/debug/jobs/<job_id>
```

这个接口会返回：

- 控制节点当前保存的 `job_meta` 记录
- 该任务哪些 `step_id` 仍被视为 `RUNNING`
- 最近 15 分钟分钟样本
- 每条最近样本是否被实时总览计入

重点检查：

- `job_meta.state` 是否仍然是 `RUNNING`
- `job_meta.end_time` 是否为空
- 是否存在某个 `step_id` 仍然没有收到 `CLOSED`
- `recent_samples` 中的 `counted_in_realtime` 是否仍为 `true`

当前实现中：

- `Epilog` 产生的 `CLOSED` 事件如果同步控制节点失败，不会再立即删除事件文件，agent 后续会继续重试
- 控制节点收到迟到的旧分钟样本时，不会再把已 `CLOSED` 的 `job_meta` 重新改回 `RUNNING`

### 1.2 调试单个任务为什么没有触发告警

如果怀疑某个任务应该触发告警，但控制节点没有生成 `alerts` 记录，可以调用：

```bash
curl http://127.0.0.1:8001/api/v1/debug/alerts/jobs/<job_id>
```

这个接口会返回：

- `runtime_minutes`
- 最近 30 分钟窗口的 `minute_count` / `minute_span`
- 最近 30 分钟窗口的 `avg_gpu_util_percent` / `avg_mem_util_percent`
- 最近 2 小时窗口的 `minute_count` / `minute_span`
- 最近 2 小时窗口的 `avg_gpu_util_percent`
- 各条 job 级告警规则当前“按逻辑是否应当触发”
- 当前数据库里已经存在的 active 告警
- 最近一小段样本预览

重点看：

- `window_30m.rule_low_util_30m_would_fire`
- `window_30m.rule_high_mem_low_gpu_would_fire`
- `window_2h.rule_low_util_2h_would_fire`
- `runtime_minutes`
- `minute_span`
- `avg_gpu_util_percent`

如果 `would_fire=true` 但 `active_alerts` 仍为空，就说明问题在控制节点 worker 扫描链路；如果 `would_fire=false`，就说明是规则条件本身还没满足。

### 1.3 调试用户级告警为什么触发/未触发

如果要定位某个用户为什么出现或没有出现 `user_low_util` 告警，可以调用：

```bash
curl http://127.0.0.1:8001/api/v1/debug/alerts/users/<user_name>
```

这个接口会返回：

- 最近 1 小时窗口的 `minute_count` / `minute_span`
- `allocated_gpu_count`
- `avg_gpu_util_percent`
- `rule_user_low_util_would_fire`
- 当前数据库里该用户的 active 告警
- 最近一小段样本预览

### 1.4 调试节点级告警为什么触发/未触发

如果要定位某个节点为什么出现或没有出现 `node_low_util` 告警，可以调用：

```bash
curl http://127.0.0.1:8001/api/v1/debug/alerts/nodes/<node_name>
```

这个接口会返回：

- 最近 1 小时窗口的 `minute_count` / `minute_span`
- `low_util_gpu_count`
- `low_util_gpu_uuids`
- `rule_node_low_util_would_fire`
- 当前数据库里该节点的 active 告警
- 最近一小段样本预览

### 2. 验证计算节点 hook

可人工模拟：

```bash
export SLURM_JOB_ID=123456
export SLURM_STEP_ID=batch
export SLURM_JOB_USER=testuser
export SLURM_JOB_UID=1000
export SLURM_JOB_GPUS=0
python3 -m gpu_monitor.node_agent register-job
```

### 3. 查看本地缓存

计算节点 SQLite：

```bash
sqlite3 /var/lib/gpu-monitor/node-agent.db "select job_id, gpu_uuid, state from active_mappings;"
sqlite3 /var/lib/gpu-monitor/node-agent.db "select count(*) from sample_queue;"
```

## 后续建议

- 为 API 增加鉴权，例如 token 或节点白名单
- 为 `SLURM_JOB_GPUS` 的不同格式补更完整的解析器
