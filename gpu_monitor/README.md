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

- 基于 `TaskProlog/TaskEpilog` + 节点 agent 事件消费维护 job-user-node-gpu 映射
- 节点端每分钟采集活跃 GPU 的 `gpu_util_percent` / `mem_used_bytes` / `mem_total_bytes` / `mem_util_percent`
- 节点端用 SQLite WAL 做本地缓存，控制节点不可达时保留最近 2 小时未送达样本
- 节点端每 5 分钟批量上报 `/api/v1/ingest/metrics`
- 控制节点提供以下 API：
  - `POST /api/v1/ingest/metrics`
  - `POST /api/v1/ingest/heartbeat`
  - `GET /api/v1/overview/realtime`
  - `GET /api/v1/jobs`
  - `GET /api/v1/jobs/{job_id}`
  - `GET /api/v1/users`
  - `GET /api/v1/users/{user_name}`
  - `GET /api/v1/nodes`
  - `GET /api/v1/nodes/{node_name}`
  - `GET /api/v1/alerts`
- 控制节点内置后台 worker：
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

最少需要：

```bash
export PYTHONPATH=/home/yxwang/LUMIA-server-management
export GPU_MONITOR_DATABASE_URL="sqlite+pysqlite:////home/yxwang/LUMIA-server-management/gpu_monitor/controller/gpu-monitor.db"
export GPU_MONITOR_API_HOST="0.0.0.0"
export GPU_MONITOR_API_PORT="8000"
export GPU_MONITOR_CLUSTER_NAME="lumia"
```

如果要切换 PostgreSQL，可直接把 `GPU_MONITOR_DATABASE_URL` 改成：

```bash
export GPU_MONITOR_DATABASE_URL="postgresql+psycopg://user:password@127.0.0.1:5432/gpu_monitor"
```

### 2. 启动 API

```bash
cd /home/yxwang/LUMIA-server-management
source .venv/bin/activate
python3 -m gpu_monitor.controller_app
```

默认监听：

- `http://127.0.0.1:8000`

本地访问示例：

```bash
curl http://127.0.0.1:8000/api/v1/overview/realtime
curl http://127.0.0.1:8000/api/v1/jobs?range=1d
curl http://127.0.0.1:8000/api/v1/alerts
```

### 3. systemd 示例

可在汇总节点创建 `/etc/systemd/system/gpu-monitor-api.service`：

```ini
[Unit]
Description=GPU Monitor API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/yxwang/LUMIA-server-management
Environment=PYTHONPATH=/home/yxwang/LUMIA-server-management
Environment=GPU_MONITOR_DATABASE_URL=sqlite+pysqlite:////home/yxwang/LUMIA-server-management/gpu_monitor/controller/gpu-monitor.db
Environment=GPU_MONITOR_API_HOST=0.0.0.0
Environment=GPU_MONITOR_API_PORT=8000
Environment=GPU_MONITOR_CLUSTER_NAME=lumia
ExecStart=/home/yxwang/LUMIA-server-management/.venv/bin/python3 -m gpu_monitor.controller_app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用方式：

```bash
systemctl daemon-reload
systemctl enable --now gpu-monitor-api.service
```

## 计算节点部署

### 1. 配置环境变量

最少需要：

```bash
export PYTHONPATH=/home/yxwang/LUMIA-server-management
export GPU_MONITOR_CLUSTER_NAME="lumia"
export GPU_MONITOR_NODE_NAME="$(hostname -s)"
export GPU_MONITOR_NODE_DB="/var/lib/gpu-monitor/node-agent.db"
export GPU_MONITOR_API_BASE_URL="http://<汇总节点IP>:8000"
export GPU_MONITOR_SAMPLE_INTERVAL_SECONDS="60"
export GPU_MONITOR_FLUSH_INTERVAL_SECONDS="300"
export GPU_MONITOR_HEARTBEAT_INTERVAL_SECONDS="300"
```

### 2. 启动节点 agent

```bash
cd /home/yxwang/LUMIA-server-management
source .venv/bin/activate
python3 -m gpu_monitor.node_agent run-agent
```

### 3. systemd 示例

在计算节点创建 `/etc/systemd/system/gpu-monitor-agent.service`：

```ini
[Unit]
Description=GPU Monitor Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/yxwang/LUMIA-server-management
Environment=PYTHONPATH=/home/yxwang/LUMIA-server-management
Environment=GPU_MONITOR_CLUSTER_NAME=lumia
Environment=GPU_MONITOR_NODE_NAME=%H
Environment=GPU_MONITOR_NODE_DB=/var/lib/gpu-monitor/node-agent.db
Environment=GPU_MONITOR_API_BASE_URL=http://<汇总节点IP>:8000
ExecStart=/home/yxwang/LUMIA-server-management/.venv/bin/python3 -m gpu_monitor.node_agent run-agent
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用方式：

```bash
mkdir -p /var/lib/gpu-monitor
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
```

在 `slurm.conf` 中配置：

```ini
Prolog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_prolog.sh
Epilog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_epilog.sh
TaskProlog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_prolog.sh
TaskEpilog=/home/yxwang/LUMIA-server-management/gpu_monitor/slurm_task_epilog.sh
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

- `Prolog/Epilog` 只保留节点级辅助逻辑
- `TaskProlog` 调用 `/usr/local/bin/get_real_gpu_id` 生成 `SLURM_REAL_GPUS`
- `TaskProlog` 再调用 `${GPU_MONITOR_PYTHON:-python3} -m gpu_monitor.node_agent emit-register-event`
- `TaskEpilog` 调用 `${GPU_MONITOR_PYTHON:-python3} -m gpu_monitor.node_agent emit-finish-event`

脚本会读取：

- `SLURM_JOB_ID`
- `SLURM_STEP_ID`
- `SLURM_JOB_USER`
- `SLURM_JOB_UID`
- `SLURM_JOB_GPUS`
- `SLURM_STEP_GPUS`
- `CUDA_VISIBLE_DEVICES`

内部统一把 `gpu_index` 转换成 `gpu_uuid` 存储。

在启用 `task/cgroup` 的集群上，推荐优先使用真实 GPU 编号：

- `SLURM_REAL_GPUS`

如果计算节点已经提供 `/usr/local/bin/get_real_gpu_id`，`slurm_task_prolog.sh` 会先执行它并导出 `SLURM_REAL_GPUS`。

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

## 实现说明与边界

- 节点采集依赖 `pynvml`，底层调用 NVML
- 当前版本默认使用 SQLite 以便快速本地部署；配置 `GPU_MONITOR_DATABASE_URL` 后可切换到 PostgreSQL
- 小时聚合与告警扫描内置在 API 进程中，方便一期落地；后续可拆分成独立 worker
- 一期未覆盖 MIG、MPS、多任务共享同一张 GPU 的精细归因
- `SLURM_JOB_GPUS` 默认按 `0,1,2` 这样的物理 GPU index 解析；如果集群里变量格式不同，需要按实际 Slurm 输出格式调整 `build_mapping_from_env`

## 验证建议

### 1. 验证汇总节点

```bash
curl http://127.0.0.1:8000/api/v1/overview/realtime
```

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

- 若要接生产，优先把控制节点数据库切到 PostgreSQL
- 为 API 增加鉴权，例如 token 或节点白名单
- 将 worker 从 API 进程拆出成单独服务
- 为 `SLURM_JOB_GPUS` 的不同格式补更完整的解析器
