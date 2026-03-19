# GPU Monitor API V1

本文档描述当前 `gpu_monitor` 实现中的 V1 API。接口前缀统一为：

```text
/api/v1
```

当前版本分两类接口：

- 节点上报接口
- 查询接口

数据格式统一为 `application/json`，时间字段统一使用 ISO 8601。

当前默认时序：

- 计算节点采样：每 15 秒一次
- 计算节点批量上报：每 1 分钟一次
- 控制节点聚合与告警扫描：每 1 分钟一次

## 1. 字段语义

### 1.1 GPU 字段

- `gpu_uuid`：任务实际分配到的 GPU 的真实 UUID
- `gpu_index`：节点上的真实物理 GPU id

在启用 `task/cgroup` 的集群中，可能出现：

- 任务内 `nvidia-smi` 显示 `GPU 0`
- API 返回 `gpu_index=3`

这表示任务内可见编号 `0` 实际对应节点物理 GPU `3`，属于正常行为。

### 1.2 range 参数

部分查询接口支持 `range`：

- `realtime`
  - 最近 15 分钟
- `1d`
  - 最近 1 天
- `1w`
  - 最近 7 天

说明：

- `realtime` 和 `1d` 主要查询分钟级数据
- `1w` 主要查询小时聚合数据

## 2. 节点上报接口

## 2.1 POST /api/v1/ingest/metrics

节点批量上报 GPU 分钟采样数据。

### 请求体

```json
{
  "node_name": "node1",
  "batch_time": "2026-03-13T11:59:00+00:00",
  "samples": [
    {
      "ts": "2026-03-13T11:58:00+00:00",
      "cluster_name": "lumia",
      "node_name": "node1",
      "job_id": "43832",
      "step_id": "0",
      "user_name": "alice",
      "uid": 1001,
      "gpu_uuid": "GPU-3ceb4eb3-567a-a23c-1804-60f30f53fdea",
      "gpu_index": 3,
      "gpu_util_percent": 81.0,
      "mem_used_bytes": 21474836480,
      "mem_total_bytes": 42949672960,
      "mem_util_percent": 50.0
    }
  ]
}
```

### 字段说明

- `node_name`：当前上报节点名
- `batch_time`：本批次上报时间
- `samples`：分钟样本数组

每条 `sample` 包含：

- `ts`：样本时间
- `cluster_name`：集群名
- `node_name`：节点名
- `job_id`：作业 ID
- `step_id`：步骤 ID
- `user_name`：用户名
- `uid`：用户 UID
- `gpu_uuid`：真实 GPU UUID
- `gpu_index`：真实物理 GPU id
- `gpu_util_percent`：GPU 利用率
- `mem_used_bytes`：显存已用字节数
- `mem_total_bytes`：显存总字节数
- `mem_util_percent`：显存利用率

### 成功响应

```json
{
  "accepted_count": 1,
  "rejected_count": 0,
  "server_time": "2026-03-13T11:59:01.123456+00:00"
}
```

### 当前实现行为

- 如果某条样本的 `sample.node_name != payload.node_name`，则该条会被拒绝
- 成功写入后会同步更新 `job_meta`

## 2.2 POST /api/v1/ingest/heartbeat

节点上报 agent 心跳。

### 请求体

```json
{
  "node_name": "node1",
  "agent_version": "1.0.0",
  "ts": "2026-03-13T12:00:00+00:00",
  "active_job_count": 2,
  "active_gpu_count": 4
}
```

### 成功响应

```json
{
  "status": "ok"
}
```

### 当前实现行为

- 同一 `node_name` 会执行覆盖更新
- 用于节点状态跟踪，不参与用户查询维度返回

## 2.3 POST /api/v1/ingest/job-state

节点 agent 在处理 `TaskProlog/TaskEpilog` 事件后，用于同步作业生命周期状态。

### 请求体

```json
{
  "job_id": "43832",
  "step_id": "0",
  "state": "CLOSED",
  "ts": "2026-03-14T01:23:45+00:00",
  "node_name": "node1"
}
```

### 成功响应

```json
{
  "status": "ok"
}
```

## 3. 查询接口

## 3.1 GET /api/v1/overview/realtime

返回最近 15 分钟实时概览。

统计口径：

- `running_job_count` 和 `allocated_gpu_count` 只统计控制节点当前标记为 `RUNNING` 的作业
- 已收到 `CLOSED` 状态同步的任务不会继续占据实时总览
- 在最近 15 分钟窗口内，每个 `job_id + step_id + node_name + gpu_uuid` 只取最新一条样本作为当前快照

### 响应示例

```json
{
  "running_job_count": 3,
  "allocated_gpu_count": 6,
  "avg_gpu_util_percent": 62.4,
  "avg_mem_util_percent": 48.7,
  "low_util_job_count": 1,
  "active_alert_count": 2
}
```

### 字段说明

- `running_job_count`：最近 15 分钟出现过样本的作业数
- `allocated_gpu_count`：当前运行作业在最近 15 分钟窗口内的 GPU 最新快照去重数
- `avg_gpu_util_percent`：当前运行 GPU 最新快照的平均 GPU 利用率
- `avg_mem_util_percent`：当前运行 GPU 最新快照的平均显存利用率
- `low_util_job_count`：当前快照里存在低利用率 GPU 的作业数
- `active_alert_count`：当前 active 告警数

## 3.2 GET /api/v1/jobs

作业列表查询。

### 查询参数

- `range`
  - 可选，默认 `realtime`
  - 取值：`realtime` | `1d` | `1w`
- `page`
  - 可选，默认 `1`
- `page_size`
  - 可选，默认 `20`
  - 最大 `200`

### 请求示例

```text
GET /api/v1/jobs?range=1d&page=1&page_size=20
```

### 响应示例

```json
{
  "items": [
    {
      "job_id": "43832",
      "user_name": "alice",
      "gpu_count": 1,
      "avg_gpu_util_percent": 81.0,
      "avg_mem_util_percent": 50.0,
      "sample_count": 12
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

### 当前实现行为

- `range=1w` 使用小时聚合表
- `range=realtime` 和 `range=1d` 使用分钟表

## 3.3 GET /api/v1/jobs/{job_id}

查询单个作业详情。

### 查询参数

- `range`
  - 可选，默认 `1d`
  - 取值：`1d` | `1w`

### 请求示例

```text
GET /api/v1/jobs/43832?range=1d
```

### `range=1d` 响应示例

```json
{
  "job_id": "43832",
  "user_name": "alice",
  "nodes": ["node1"],
  "gpus": ["GPU-3ceb4eb3-567a-a23c-1804-60f30f53fdea"],
  "range": "1d",
  "series": [
    {
      "ts": "2026-03-13T11:58:00+00:00",
      "node_name": "node1",
      "gpu_uuid": "GPU-3ceb4eb3-567a-a23c-1804-60f30f53fdea",
      "gpu_util_percent": 81.0,
      "mem_util_percent": 50.0
    }
  ]
}
```

### `range=1w` 响应示例

```json
{
  "job_id": "43832",
  "range": "1w",
  "series": [
    {
      "ts": "2026-03-13T11:00:00+00:00",
      "avg_gpu_util_percent": 65.2,
      "avg_mem_util_percent": 48.9,
      "gpu_count": 1
    }
  ]
}
```

### 错误响应

```json
{
  "detail": "job not found"
}
```

状态码：

- `404`

## 3.4 GET /api/v1/users

用户列表查询。

### 查询参数

- `range`
  - 可选，默认 `realtime`
  - 取值：`realtime` | `1d` | `1w`

### 响应示例

```json
{
  "items": [
    {
      "user_name": "alice",
      "running_job_count": 2,
      "allocated_gpu_count": 4,
      "avg_gpu_util_percent": 54.2,
      "avg_mem_util_percent": 41.1
    }
  ],
  "total": 1
}
```

## 3.5 GET /api/v1/users/{user_name}

用户详情查询。

### 查询参数

- `range`
  - 可选，默认 `1d`
  - 取值：`1d` | `1w`

### `range=1d` 响应示例

```json
{
  "user_name": "alice",
  "running_jobs": ["43832", "43833"],
  "nodes": ["node1", "node2"],
  "range": "1d",
  "series": [
    {
      "ts": "2026-03-13T11:58:00+00:00",
      "job_id": "43832",
      "node_name": "node1",
      "gpu_util_percent": 81.0,
      "mem_util_percent": 50.0
    }
  ]
}
```

### `range=1w` 响应示例

```json
{
  "user_name": "alice",
  "range": "1w",
  "series": [
    {
      "ts": "2026-03-13T11:00:00+00:00",
      "running_job_count": 2,
      "allocated_gpu_count": 4,
      "avg_gpu_util_percent": 54.2,
      "avg_mem_util_percent": 41.1,
      "sample_count": 120
    }
  ]
}
```

## 3.6 GET /api/v1/nodes

节点列表查询。

### 查询参数

- `range`
  - 可选，默认 `realtime`
  - 取值：`realtime` | `1d` | `1w`

### 响应示例

```json
{
  "items": [
    {
      "node_name": "node1",
      "gpu_allocated": 4,
      "avg_gpu_util_percent": 62.1,
      "avg_mem_util_percent": 46.8
    }
  ],
  "total": 1
}
```

## 3.7 GET /api/v1/nodes/{node_name}

节点详情查询。

### 查询参数

- `range`
  - 可选，默认 `1d`
  - 取值：`1d` | `1w`

### `range=1d` 响应示例

```json
{
  "node_name": "node1",
  "active_jobs": ["43832", "43833"],
  "range": "1d",
  "series": [
    {
      "ts": "2026-03-13T11:58:00+00:00",
      "job_id": "43832",
      "user_name": "alice",
      "gpu_uuid": "GPU-3ceb4eb3-567a-a23c-1804-60f30f53fdea",
      "gpu_util_percent": 81.0,
      "mem_util_percent": 50.0
    }
  ]
}
```

### `range=1w` 响应示例

```json
{
  "node_name": "node1",
  "range": "1w",
  "series": [
    {
      "ts": "2026-03-13T11:00:00+00:00",
      "allocated_gpu_count": 4,
      "avg_gpu_util_percent": 62.1,
      "avg_mem_util_percent": 46.8,
      "sample_count": 240
    }
  ]
}
```

## 3.8 GET /api/v1/alerts

告警列表查询。

### 查询参数

- `status`
  - 可选，默认 `active`
- `entity_type`
  - 可选
  - 取值：`job` | `user` | `node`

### 请求示例

```text
GET /api/v1/alerts?status=active&entity_type=job
```

### 响应示例

```json
{
  "items": [
    {
      "id": 1,
      "entity_type": "job",
      "entity_id": "43832",
      "level": "warning",
      "rule_name": "low_util_30m",
      "summary": "job 43832 avg gpu util 8.50% in 30m",
      "start_time": "2026-03-13T11:30:00+00:00",
      "last_seen_time": "2026-03-13T11:35:00+00:00",
      "end_time": null,
      "status": "active"
    }
  ],
  "total": 1
}
```

## 4. 错误码

当前实现中常见错误码：

- `400`
  - 非法 `range`
- `404`
  - `job` / `user` / `node` 不存在
- `422`
  - 请求体字段校验失败

## 5. 告警规则

当前 worker 已实现如下规则：

- `low_util_30m`
  - job 最近 30 分钟平均 `gpu_util_percent < 10`
- `high_mem_low_gpu`
  - job 最近 30 分钟平均 `mem_util_percent > 60` 且平均 `gpu_util_percent < 10`
- `low_util_2h`
  - job 最近 2 小时平均 `gpu_util_percent < 5`
- `user_low_util`
  - user 最近 1 小时占用 GPU 数 `>= 4` 且平均 `gpu_util_percent < 15`
- `node_low_util`
  - node 最近 1 小时至少 2 张活跃 GPU 利用率低于 `10`

规则计算方式：

- 所有时间窗口规则都按分钟桶跨度计算，不按样本条数计算
- 对多卡任务、多卡用户、多卡节点，会先在同一分钟内做聚合，再对分钟窗口求平均
- 因此两卡任务运行 20 分钟不会因为产生了约 40 条样本就提前满足“30 分钟规则”
- 如果窗口内偶发缺少少量分钟样本，只要整体时间跨度达到阈值，规则仍会生效

## 6. 当前限制

- 当前 API 没有鉴权
- 当前接口没有统一 OpenAPI 导出文档文件，本说明以代码实现为准
- `jobs/{job_id}` 当前只返回 GPU UUID 列表，不单独返回真实物理 GPU id 列表
- `1w` 范围依赖后台小时聚合任务
- 当前返回结构偏管理查询用途，不是 Prometheus 风格指标接口

## 7. 重启与数据持久化

### 7.1 控制节点 `gpu-monitor-api` / `gpu-monitor-worker` 重启

- 控制节点分钟数据、小时聚合、告警都保存在数据库中
- API 或 worker 进程重启都不会清空这些数据
- 计算节点在 API 不可达时，会把未送达样本保存在本地 SQLite 队列中
- API 恢复后，agent 会继续补传

### 7.2 计算节点 `gpu-monitor-agent` 重启

- 节点本地 `active_mappings` 与 `sample_queue` 使用 SQLite 持久化
- agent 重启后会继续读取已有映射与未送达样本
- 当前实现会优先处理 task 事件并执行采样，再做 stale mapping 清理，避免长任务因为 agent 重启被误判结束

### 7.3 仍可能丢失数据的边界

- 控制节点持续不可达时间超过 `GPU_MONITOR_UNDELIVERED_RETENTION_HOURS`
- 本地未送达样本数超过 `GPU_MONITOR_UNDELIVERED_MAX_RECORDS`

在上述情况下，节点会清理最旧的未送达数据以保护本地磁盘空间。
