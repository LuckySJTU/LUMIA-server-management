Slurm 集群 GPU 用量监控系统设计说明（一期）

1. 目标与范围

1.1 目标

构建一套面向 Slurm 集群的 GPU 用量监控系统，能够：
	•	识别每个 Slurm 任务在各节点上实际分配到的 GPU
	•	每分钟采集一次该 GPU 的 gpu util 和 memory usage
	•	在控制节点集中汇总
	•	提供按任务 / 用户 / 节点三个维度的查询与展示
	•	支持实时、过去一天、过去一周的查看
	•	保存数据 30 天
	•	自动发现“长期低利用率占卡”等异常情况

Slurm 原生支持将 GPU 作为 GRES 资源进行调度，并可通过相关机制提供 GPU 归属与记账信息；NVIDIA 的 NVML 是 nvidia-smi 的底层库，可直接获取 GPU 利用率和显存信息；DCGM 也支持低开销的持续 telemetry 和 job 级分析能力。基于这些能力，可以把“任务归属”和“GPU 指标采集”拆开设计。 ￼

1.2 一期范围

一期只覆盖以下场景：
	•	Slurm 常规 gres/gpu 调度
	•	非 MIG 主场景
	•	非 MPS 主场景
	•	指标仅采：
	•	gpu util
	•	memory usage
	•	采样周期固定为 1 分钟
	•	数据最多保留 1 个月

1.3 非目标

一期先不重点覆盖：
	•	MIG 细粒度实例级展示
	•	进程级 GPU 归因
	•	容器内部 PID 级拆分
	•	秒级实时流式看板
	•	复杂 AI 异常检测模型

⸻

2. 总体架构

系统分为 6 个核心模块：
	1.	Slurm 任务映射模块
	2.	节点本地采集模块
	3.	节点本地缓存与上报模块
	4.	控制节点汇总与存储模块
	5.	异常检测模块
	6.	展示模块

核心原则只有两条：
	•	归属关系以 Slurm 为准
	•	采集动作在计算节点本地完成

这样做的原因是：Slurm 最清楚“这张卡属于谁”，而 NVML / DCGM 最擅长“这张卡现在用了多少”。Slurm 官方文档对 GRES/GPU 调度与 accounting 做了明确说明；NVML 官方说明其是线程安全的 GPU 监控管理接口，且是 nvidia-smi 的底层；DCGM 官方说明其可提供低开销持续 telemetry，并支持 job 级分析。 ￼

2.1 架构关系

逻辑链路如下：
	•	Slurm 作业启动
	•	Prolog / Epilog 更新“任务-GPU映射”
	•	节点 agent 每分钟读取活跃映射
	•	节点 agent 对对应 GPU 采样
	•	节点 agent 批量上报控制节点
	•	控制节点写入分钟表
	•	后台聚合为小时表
	•	展示层查询实时 / 日 / 周数据
	•	告警模块扫描低利用率异常

⸻

3. 模块设计

3.1 Slurm 任务映射模块

3.1.1 职责

维护当前活跃的 job / user / node / gpu 映射关系，作为整套系统的“归属事实来源”。

3.1.2 输入

来自 Slurm 的作业上下文信息，建议主要通过：
	•	Prolog 或 TaskProlog
	•	Epilog 或 TaskEpilog

可获取的信息包括：
	•	job_id
	•	step_id
	•	user
	•	uid
	•	node
	•	SLURM_JOB_GPUS
	•	作业内可见 GPU 编号
	•	作业启动时间

Slurm 的 GRES 文档明确说明了 GPU 作为 GRES 资源的分配方式，以及 AccountingStorageTRES=gres/gpu 下相关 GPU 记账行为。 ￼

3.1.3 输出

在每个计算节点维护一份本地活跃映射表。推荐字段：
	•	job_id
	•	step_id
	•	user_name
	•	uid
	•	node_name
	•	gpu_uuid
	•	gpu_index
	•	start_time
	•	last_seen_time
	•	state

3.1.4 实现建议

建议每个节点本地维护：
	•	内存态缓存
	•	SQLite 持久化

原因：
	•	节点 agent 本地读取快
	•	重启后可恢复
	•	比 JSON 文件更稳
	•	比每次 squeue 查询更轻

3.1.5 编号规范

内部统一使用 gpu_uuid 作为主标识，gpu_index 只用于展示。
NVML 官方支持通过 UUID、PCI Bus ID、index 等方式获取设备句柄，其中 UUID 是更稳定的标识。 ￼

3.1.6 状态机

映射记录状态建议只有三种：
	•	RUNNING
	•	ENDING
	•	CLOSED

处理方式：
	•	Prolog 写入 RUNNING
	•	Epilog 先标记 ENDING
	•	数据 flush 完后标记 CLOSED

3.1.7 兜底校验

为了防止 Prolog/Epilog 异常未执行，控制节点每 5 分钟做一次低频校验：
	•	拉取当前活跃作业列表
	•	检查节点上报中是否有“已结束仍活跃”的脏映射
	•	超时未更新的映射自动清理

⸻

3.2 节点本地采集模块

3.2.1 职责

每分钟对“当前被 Slurm 分配中的 GPU”采集一次指标。

3.2.2 指标范围

一期只采两个核心指标：
	•	gpu_util
	•	memory_usage

具体保存形式建议是：
	•	gpu_util_percent
	•	mem_used_bytes
	•	mem_total_bytes
	•	mem_util_percent

NVML 官方说明它可用于监控 GPU 状态，且是 nvidia-smi 的底层；旧版 NVML 文档对 utilization 字段的定义也明确指出，gpu 表示过去采样周期内执行 kernel 的时间占比，memory 表示显存读写活动占比。你的需求里“memory usage”更适合记录 used/total 以及换算后的 mem_util_percent。 ￼

3.2.3 采样策略

固定为：
	•	每 1 分钟采样一次

只对以下 GPU 采样：
	•	当前节点上
	•	正被 Slurm 活跃任务占用的 GPU

不对以下对象高频采样：
	•	空闲 GPU
	•	未分配 GPU
	•	无活跃作业的节点 GPU

3.2.4 采集方案选择

一期建议优先用 NVML：
	•	依赖少
	•	开销低
	•	指标刚好够用
	•	集成简单

DCGM 作为二期可选增强方案。因为 DCGM 更偏向长期统一 telemetry 体系，官方也强调其支持低开销的持续监控与 job-level analysis。 ￼

3.2.5 样本结构

每条分钟样本建议包含：
	•	ts
	•	cluster_name
	•	node_name
	•	job_id
	•	step_id
	•	user_name
	•	uid
	•	gpu_uuid
	•	gpu_index
	•	gpu_util_percent
	•	mem_used_bytes
	•	mem_total_bytes
	•	mem_util_percent

3.2.6 采集时序

每轮采样流程：
	1.	读取本地活跃映射表
	2.	去重得到本节点活跃 GPU 列表
	3.	对每张 GPU 读取 NVML 指标
	4.	按映射关系复制到对应 job 记录
	5.	写入本地缓存队列

3.2.7 负载控制

采集模块的低负载要求如下：
	•	常驻进程，不反复拉起 shell
	•	不高频调用 nvidia-smi
	•	尽量避免控制节点主动远程拉取
	•	单轮读取仅针对活跃 GPU

NVML 官方说明其线程安全，适合第三方监控应用构建。 ￼

⸻

3.3 节点本地缓存与上报模块

3.3.1 职责

在节点侧实现短期可靠缓存与批量上报。

3.3.2 设计目标

解决两个问题：
	•	控制节点短时不可达时不丢数据
	•	避免每分钟每条样本都单独发请求

3.3.3 缓存介质

建议用本地 SQLite，开启 WAL。

原因：
	•	轻量
	•	宕机恢复简单
	•	支持批量读取和删除
	•	不引入额外中间件

3.3.4 上报策略

建议：
	•	采样：每 1 分钟
	•	上报：每 5 分钟批量一次

每次上报内容：
	•	本节点最近 5 分钟的全部分钟样本
	•	节点状态心跳
	•	当前活跃任务概览

3.3.5 重试策略

若控制节点不可达：
	•	标记本批次未送达
	•	下一轮继续重试
	•	本地缓存最大保留 2 小时未上报数据

若超过 2 小时仍未送达：
	•	继续保留最新数据
	•	清理最旧数据
	•	记录本地日志

3.3.6 上报协议

推荐统一 HTTP API：
	•	简单
	•	调试方便
	•	易接入已有 Web 后端

后续若吞吐明显增大，再考虑 gRPC。

⸻

3.4 控制节点汇总与存储模块

3.4.1 职责

负责接收、入库、聚合、查询。

3.4.2 数据层分级

推荐三层数据：

第一层：实时缓存
保存当前活跃任务的最新状态。

用途：
	•	实时总览
	•	当前任务列表
	•	当前用户视图
	•	当前节点视图

建议保存内容：
	•	每个 job 的最新一分钟均值
	•	每个 user 的当前聚合值
	•	每个 node 的当前聚合值

可放 Redis，也可以直接放数据库热点表。

第二层：分钟级明细表
保存最近 7 天的分钟级原始样本。

用途：
	•	实时页回看
	•	过去一天曲线
	•	精细异常检测

第三层：小时级聚合表
保存最近 30 天的小时级聚合结果。

用途：
	•	过去一周趋势
	•	周报/月内分析
	•	历史视图加速

3.4.3 存储选型

推荐：
	•	PostgreSQL / TimescaleDB

原因：
	•	适合多维过滤
	•	适合时间序列查询
	•	方便做 retention 与连续聚合
	•	后端开发成本低

3.4.4 表设计

表 1：job_meta
任务元信息表

字段建议：
	•	job_id
	•	step_id
	•	user_name
	•	uid
	•	partition_name
	•	account_name
	•	submit_time
	•	start_time
	•	end_time
	•	state
	•	node_list
	•	gpu_count

表 2：gpu_usage_minute
分钟级原始表

字段建议：
	•	ts
	•	job_id
	•	step_id
	•	user_name
	•	uid
	•	node_name
	•	gpu_uuid
	•	gpu_index
	•	gpu_util_percent
	•	mem_used_bytes
	•	mem_total_bytes
	•	mem_util_percent

保留时间：
	•	7 天

表 3：job_usage_hourly
任务级小时聚合表

字段建议：
	•	hour_ts
	•	job_id
	•	user_name
	•	gpu_count
	•	avg_gpu_util_percent
	•	max_gpu_util_percent
	•	avg_mem_util_percent
	•	max_mem_util_percent
	•	sample_count

保留时间：
	•	30 天

表 4：user_usage_hourly
用户级小时聚合表

字段建议：
	•	hour_ts
	•	user_name
	•	running_job_count
	•	allocated_gpu_count
	•	avg_gpu_util_percent
	•	avg_mem_util_percent
	•	sample_count

表 5：node_usage_hourly
节点级小时聚合表

字段建议：
	•	hour_ts
	•	node_name
	•	allocated_gpu_count
	•	avg_gpu_util_percent
	•	avg_mem_util_percent
	•	sample_count

表 6：alerts
异常事件表

字段建议：
	•	alert_id
	•	entity_type (job / user / node)
	•	entity_id
	•	level
	•	rule_name
	•	summary
	•	start_time
	•	last_seen_time
	•	end_time
	•	status (active / resolved)

3.4.5 聚合作业

控制节点定时执行两个后台任务：

分钟到小时聚合
每小时执行一次：
	•	从分钟表聚合出任务级小时表
	•	从分钟表聚合出用户级小时表
	•	从分钟表聚合出节点级小时表

旧数据清理
每天执行一次：
	•	删除超过 7 天的分钟表数据
	•	删除超过 30 天的小时表和告警数据

⸻

3.5 异常检测模块

3.5.1 职责

识别长期低效用卡的任务、用户和节点。

3.5.2 检测方式

一期使用规则引擎，不做复杂模型。

3.5.3 规则集

规则 A：任务长时间低利用率
触发条件：
	•	任务运行时长 ≥ 30 分钟
	•	最近 30 分钟平均 gpu_util < 10%

级别：
	•	warning

规则 B：任务长期极低利用率
触发条件：
	•	任务运行时长 ≥ 2 小时
	•	最近 2 小时平均 gpu_util < 5%

级别：
	•	critical

规则 C：显存高但算力低
触发条件：
	•	最近 30 分钟平均 mem_util > 60%
	•	最近 30 分钟平均 gpu_util < 10%

解释意义：
	•	模型进显存了，但几乎没算
	•	可能卡在 I/O、同步、死锁、数据加载等环节

规则 D：用户级低效占卡
触发条件：
	•	用户当前占用 GPU 数 ≥ 4
	•	最近 1 小时用户整体平均 gpu_util < 15%

规则 E：节点级异常占卡
触发条件：
	•	节点上多个活跃 GPU 在最近 1 小时平均 gpu_util < 10%
	•	且这些 GPU 已分配给活跃 job

3.5.4 检测周期

每 5 分钟 扫描一次即可。

3.5.5 状态流转

告警状态：
	•	新触发：active
	•	持续存在：更新时间戳
	•	条件消失：resolved

3.5.6 输出

输出到：
	•	alerts 表
	•	实时总览页
	•	异常页
	•	任务详情页 / 用户详情页 / 节点详情页

⸻

3.6 展示模块

展示层建议做成 5 个页面。

页面 1：实时总览页

目标

管理员打开后快速了解集群当前 GPU 资源状态。

展示内容
	•	当前运行 GPU 任务数
	•	当前占用 GPU 总数
	•	当前平均 GPU 利用率
	•	当前平均显存利用率
	•	当前低利用率任务数
	•	当前异常用户数

关键组件
	•	集群概览卡片
	•	节点热力图
	•	当前最异常的任务 TopN
	•	当前最异常的用户 TopN

数据来源
	•	实时缓存
	•	当前活跃告警表

⸻

页面 2：按任务视图

列表字段
	•	job_id
	•	user_name
	•	partition
	•	runtime
	•	gpu_count
	•	node_count
	•	current_avg_gpu_util
	•	current_avg_mem_util
	•	1d_avg_gpu_util
	•	1w_avg_gpu_util
	•	alert_status

详情页内容
	•	基本信息
	•	节点分布
	•	GPU 分布
	•	最近 24 小时曲线
	•	最近 7 天小时趋势
	•	峰值显存利用率
	•	低利用率时间占比
	•	告警历史

查询来源
	•	实时：实时缓存
	•	1 天：分钟表
	•	1 周：小时表

⸻

页面 3：按用户视图

列表字段
	•	user_name
	•	running_jobs
	•	allocated_gpus
	•	current_avg_gpu_util
	•	current_avg_mem_util
	•	1d_avg_gpu_util
	•	1w_avg_gpu_util
	•	low_util_job_count

详情页内容
	•	当前活跃任务列表
	•	最近 24 小时 GPU 利用率趋势
	•	最近 7 天趋势
	•	用户级异常记录
	•	低利用率任务排名

⸻

页面 4：按节点视图

列表字段
	•	node_name
	•	gpu_total
	•	gpu_allocated
	•	current_avg_gpu_util
	•	current_avg_mem_util
	•	1d_avg_gpu_util
	•	1w_avg_gpu_util
	•	abnormal_gpu_count

详情页内容
	•	当前每张 GPU 对应 job / user
	•	最近 24 小时 GPU 曲线
	•	最近 7 天节点小时趋势
	•	节点异常列表

⸻

页面 5：异常页

分类
	•	低利用率任务
	•	低利用率用户
	•	显存高但算力低
	•	节点级异常

列表字段
	•	告警级别
	•	类型
	•	对象
	•	持续时间
	•	当前 gpu_util
	•	过去1h平均 gpu_util
	•	过去1h平均 mem_util
	•	开始时间
	•	状态

支持筛选
	•	按告警级别
	•	按用户
	•	按节点
	•	按分区
	•	按状态

⸻

4. 数据流设计

4.1 作业启动流程
	1.	Slurm 调度作业到目标节点
	2.	节点 Prolog / TaskProlog 获取任务上下文
	3.	写入本地 job_gpu_mapping_current
	4.	节点 agent 发现新映射，纳入采样集合
	5.	控制节点记录或更新 job_meta

4.2 采样流程
	1.	节点 agent 每分钟触发一次
	2.	读取活跃映射
	3.	使用 NVML 按 GPU UUID 获取 utilization 和 memory 信息
	4.	生成分钟样本
	5.	写入本地缓存

4.3 上报流程
	1.	每 5 分钟将本地未上报样本打包
	2.	发送至控制节点 /ingest/metrics
	3.	控制节点校验并写入 gpu_usage_minute
	4.	更新实时缓存
	5.	返回成功状态
	6.	节点删除已确认数据

4.4 聚合流程
	1.	每小时定时任务运行
	2.	从分钟表聚合生成任务级、用户级、节点级小时表
	3.	更新或插入新记录

4.5 告警流程
	1.	每 5 分钟执行规则扫描
	2.	满足规则则新建或更新 alerts
	3.	不再满足则将 alerts 标记为 resolved
	4.	实时页与异常页读取活动告警

4.6 作业结束流程
	1.	Epilog 触发，节点将映射标记为 ENDING
	2.	agent 完成最后一次数据 flush
	3.	映射状态改为 CLOSED
	4.	控制节点更新 job_meta.end_time

⸻

5. 接口设计

5.1 节点上报接口

POST /api/v1/ingest/metrics

请求体建议包含：
	•	node_name
	•	batch_time
	•	samples: []

每条 sample 含：
	•	ts
	•	job_id
	•	step_id
	•	user_name
	•	uid
	•	gpu_uuid
	•	gpu_index
	•	gpu_util_percent
	•	mem_used_bytes
	•	mem_total_bytes
	•	mem_util_percent

返回：
	•	accepted_count
	•	rejected_count
	•	server_time

5.2 节点心跳接口

POST /api/v1/ingest/heartbeat

字段：
	•	node_name
	•	agent_version
	•	ts
	•	active_job_count
	•	active_gpu_count

5.3 查询接口

建议最少提供：
	•	GET /api/v1/overview/realtime
	•	GET /api/v1/jobs
	•	GET /api/v1/jobs/{job_id}
	•	GET /api/v1/users
	•	GET /api/v1/users/{user_name}
	•	GET /api/v1/nodes
	•	GET /api/v1/nodes/{node_name}
	•	GET /api/v1/alerts

查询参数支持：
	•	range=realtime|1d|1w
	•	page
	•	page_size
	•	sort_by
	•	filters

⸻

6. 部署设计

6.1 角色划分

计算节点

部署：
	•	gpu-monitor-agent
	•	本地 SQLite
	•	Slurm Prolog / Epilog 集成脚本

控制节点

部署：
	•	gpu-monitor-api
	•	gpu-monitor-worker
	•	PostgreSQL / TimescaleDB
	•	Redis（可选）
	•	Web 前端

6.2 进程划分

节点侧

一个常驻服务即可：
	•	agent
	•	负责读取映射
	•	负责采样
	•	负责缓存
	•	负责上报

控制侧

建议拆成三个服务：
	•	api
	•	接收上报
	•	提供查询接口
	•	worker
	•	聚合任务
	•	异常扫描
	•	retention 清理
	•	web
	•	页面展示

6.3 高可用建议

一期可不做复杂 HA，但要做到：
	•	节点 agent 可重启恢复
	•	控制节点数据库可每日备份
	•	采集链路短时中断不丢最近 2 小时数据

⸻

7. 性能与负载控制

7.1 设计约束

为了尽量不给集群增加额外负载，必须遵守：
	•	只采集已分配 GPU
	•	采样固定为每分钟一次
	•	节点本地采样，控制节点不主动拉
	•	批量上报，不逐条实时发送
	•	历史查询优先走聚合表

7.2 数据量估算

假设：
	•	100 台 GPU 节点
	•	每台平均 8 张卡
	•	高峰时 600 张 GPU 活跃
	•	每分钟每 GPU 一条样本

则分钟样本量约为：
	•	600 条 / 分钟
	•	864,000 条 / 天
	•	7 天约 600 万条级别

这个量级对于 PostgreSQL / TimescaleDB 的分钟明细 + 小时聚合方案是可控的，前提是：
	•	分区合理
	•	建索引适度
	•	旧数据定期清理

⸻

8. 风险与边界

8.1 MIG

Slurm 官方文档说明，对 NVIDIA MIG，NVML 不支持用于 Slurm 的 gpumem / gpuutil accounting，因此 MIG 场景不能直接套用普通整卡逻辑。若集群大量使用 MIG，需要单独做二期适配。 ￼

8.2 MPS / GPU 共享

若一张 GPU 可同时归属多个任务，则“job 独占 GPU”的归属前提不成立，需要做更细的进程级归因。一期先不覆盖。

8.3 Slurm 钩子失败

若 Prolog / Epilog 偶发失败，可能导致脏映射。
因此必须保留低频兜底清理逻辑。

8.4 节点时间漂移

分钟级采样依赖节点时间较准。建议节点统一做 NTP 同步。

⸻

9. 实施计划

阶段 1：打通基础链路

目标：
	•	节点能知道 job-user-gpu 映射
	•	每分钟采样成功
	•	能上报控制节点
	•	能入分钟表

交付物：
	•	节点 agent
	•	Prolog / Epilog 集成
	•	控制节点接收 API
	•	gpu_usage_minute 表

阶段 2：完成查询与聚合

目标：
	•	实现实时查询
	•	实现过去一天查询
	•	实现过去一周小时聚合查询

交付物：
	•	小时聚合作业
	•	job_usage_hourly
	•	user_usage_hourly
	•	node_usage_hourly

阶段 3：完成告警能力

目标：
	•	低利用率任务告警
	•	低利用率用户告警
	•	显存高但算力低告警

交付物：
	•	alerts 表
	•	规则扫描 worker
	•	异常页

阶段 4：完成前端页面

目标：
	•	实时总览页
	•	任务页
	•	用户页
	•	节点页
	•	异常页

⸻

10. 最终推荐的工程落地方案

一期建议采用下面这套组合：
	•	Slurm 映射：Prolog / Epilog + 节点本地 SQLite
	•	节点采集：NVML 常驻 agent
	•	缓存与上报：SQLite WAL + 5 分钟批量 HTTP push
	•	控制节点存储：PostgreSQL / TimescaleDB
	•	聚合与异常：后台 worker 定时任务
	•	展示：Web 页面，支持任务 / 用户 / 节点 / 异常 4 类核心视图

这套方案的优点是：
	•	满足你要求的全部查询维度
	•	负载低
	•	数据结构清晰
	•	容易上线
	•	后续能平滑演进到 DCGM / Prometheus / Grafana 体系
