import { onMounted, onUnmounted, ref } from 'vue'
import type { Ref } from 'vue'
import { useRESTAPI } from '@/composables/RESTAPI'
import { useRuntimeStore } from '@/stores/runtime'

export type GpuMonitorListRange = 'realtime' | '1d' | '1w'
export type GpuMonitorDetailRange = '1d' | '1w'
export type GpuMonitorOverviewHistoryRange = '7d' | '30d'

export interface GpuMonitorOverviewRealtime {
  running_job_count: number
  allocated_gpu_count: number
  avg_gpu_util_percent: number
  avg_mem_util_percent: number
  low_util_job_count: number
  active_alert_count: number
}

export interface GpuMonitorOverviewHistoryPoint {
  ts: string
  running_job_count: number
  allocated_gpu_count: number
  avg_gpu_util_percent: number
  avg_mem_util_percent: number
  low_util_job_count: number
  active_alert_count: number
}

export interface GpuMonitorOverviewHistoryResponse {
  range: GpuMonitorOverviewHistoryRange
  interval_minutes: number
  series: GpuMonitorOverviewHistoryPoint[]
}

export interface GpuMonitorJobsListItem {
  job_id: string
  user_name: string
  gpu_count: number
  avg_gpu_util_percent: number
  avg_mem_util_percent: number
  sample_count: number
}

export interface GpuMonitorJobsListResponse {
  items: GpuMonitorJobsListItem[]
  page: number
  page_size: number
  total: number
}

export interface GpuMonitorJobSeriesRealtimePoint {
  ts: string
  node_name: string
  gpu_uuid: string
  gpu_util_percent: number
  mem_util_percent: number
}

export interface GpuMonitorJobSeriesAggregatePoint {
  ts: string
  avg_gpu_util_percent: number
  avg_mem_util_percent: number
  gpu_count: number
}

export interface GpuMonitorJobDetailRealtime {
  job_id: string
  user_name: string
  nodes: string[]
  gpus: string[]
  range: '1d'
  series: GpuMonitorJobSeriesRealtimePoint[]
}

export interface GpuMonitorJobDetailAggregate {
  job_id: string
  range: '1w'
  series: GpuMonitorJobSeriesAggregatePoint[]
}

export type GpuMonitorJobDetail = GpuMonitorJobDetailRealtime | GpuMonitorJobDetailAggregate

export interface GpuMonitorNodesListItem {
  node_name: string
  gpu_allocated: number
  avg_gpu_util_percent: number
  avg_mem_util_percent: number
}

export interface GpuMonitorNodesListResponse {
  items: GpuMonitorNodesListItem[]
  total: number
}

export interface GpuMonitorUsersListItem {
  user_name: string
  running_job_count: number
  allocated_gpu_count: number
  avg_gpu_util_percent: number
  avg_mem_util_percent: number
}

export interface GpuMonitorUsersListResponse {
  items: GpuMonitorUsersListItem[]
  total: number
}

export interface GpuMonitorAlertItem {
  id: number
  entity_type: 'job' | 'user' | 'node'
  entity_id: string
  level: 'warning' | 'critical' | string
  rule_name: string
  summary: string
  start_time: string
  last_seen_time: string
  end_time: string | null
  status: string
}

export interface GpuMonitorAlertsResponse {
  items: GpuMonitorAlertItem[]
  total: number
}

export interface GpuMonitorNodeSeriesRealtimePoint {
  ts: string
  job_id: string
  user_name: string
  gpu_uuid: string
  gpu_util_percent: number
  mem_util_percent: number
}

export interface GpuMonitorNodeSeriesAggregatePoint {
  ts: string
  allocated_gpu_count: number
  avg_gpu_util_percent: number
  avg_mem_util_percent: number
  sample_count: number
}

export interface GpuMonitorNodeDetailRealtime {
  node_name: string
  active_jobs: string[]
  range: '1d'
  series: GpuMonitorNodeSeriesRealtimePoint[]
}

export interface GpuMonitorNodeDetailAggregate {
  node_name: string
  range: '1w'
  series: GpuMonitorNodeSeriesAggregatePoint[]
}

export type GpuMonitorNodeDetail = GpuMonitorNodeDetailRealtime | GpuMonitorNodeDetailAggregate

export interface GpuMonitorPoller<ResponseType> {
  data: Ref<ResponseType | undefined>
  unable: Ref<boolean>
  loaded: Ref<boolean>
  error: Ref<Error | undefined>
  refresh: () => Promise<void>
  restart: () => Promise<void>
}

const GPU_MONITOR_MAX_PAGE_SIZE = 200

function average(values: number[]): number | null {
  if (!values.length) {
    return null
  }
  return values.reduce((result, value) => result + value, 0) / values.length
}

export function averageGpuMetric(values: number[]): number | null {
  return average(values)
}

export function formatGpuPercent(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return '-'
  }
  return `${value.toFixed(1)}%`
}

export function useGpuMonitorAPI() {
  const restAPI = useRESTAPI()

  async function request<ResponseType>(resource: string): Promise<ResponseType> {
    return await restAPI.get<ResponseType>(resource)
  }

  async function overviewRealtime(cluster: string): Promise<GpuMonitorOverviewRealtime> {
    return await request<GpuMonitorOverviewRealtime>(`/agents/${cluster}/gpu-monitor/overview`)
  }

  async function overviewHistory(
    cluster: string,
    range: GpuMonitorOverviewHistoryRange = '7d'
  ): Promise<GpuMonitorOverviewHistoryResponse> {
    return await request<GpuMonitorOverviewHistoryResponse>(
      `/agents/${cluster}/gpu-monitor/overview/history?range=${range}`
    )
  }

  async function jobs(
    cluster: string,
    range: GpuMonitorListRange = 'realtime',
    page: number = 1,
    pageSize: number = GPU_MONITOR_MAX_PAGE_SIZE
  ): Promise<GpuMonitorJobsListResponse> {
    return await request<GpuMonitorJobsListResponse>(
      `/agents/${cluster}/gpu-monitor/jobs?range=${range}&page=${page}&page_size=${pageSize}`
    )
  }

  async function jobsAll(
    cluster: string,
    range: GpuMonitorListRange = 'realtime'
  ): Promise<GpuMonitorJobsListItem[]> {
    const firstPage = await jobs(cluster, range, 1, GPU_MONITOR_MAX_PAGE_SIZE)
    const result = [...firstPage.items]
    const totalPages = Math.ceil(firstPage.total / firstPage.page_size)

    for (let page = 2; page <= totalPages; page += 1) {
      const nextPage = await jobs(cluster, range, page, GPU_MONITOR_MAX_PAGE_SIZE)
      result.push(...nextPage.items)
    }

    return result
  }

  async function job(
    cluster: string,
    jobId: number,
    range: GpuMonitorDetailRange = '1d'
  ): Promise<GpuMonitorJobDetail> {
    return await request<GpuMonitorJobDetail>(
      `/agents/${cluster}/gpu-monitor/job/${jobId}?range=${range}`
    )
  }

  async function nodes(
    cluster: string,
    range: GpuMonitorListRange = 'realtime'
  ): Promise<GpuMonitorNodesListResponse> {
    return await request<GpuMonitorNodesListResponse>(
      `/agents/${cluster}/gpu-monitor/nodes?range=${range}`
    )
  }

  async function node(
    cluster: string,
    nodeName: string,
    range: GpuMonitorDetailRange = '1d'
  ): Promise<GpuMonitorNodeDetail> {
    return await request<GpuMonitorNodeDetail>(
      `/agents/${cluster}/gpu-monitor/node/${encodeURIComponent(nodeName)}?range=${range}`
    )
  }

  async function users(
    cluster: string,
    range: GpuMonitorListRange = 'realtime'
  ): Promise<GpuMonitorUsersListResponse> {
    return await request<GpuMonitorUsersListResponse>(
      `/agents/${cluster}/gpu-monitor/users?range=${range}`
    )
  }

  async function alerts(
    cluster: string,
    status: string = 'active'
  ): Promise<GpuMonitorAlertsResponse> {
    return await request<GpuMonitorAlertsResponse>(
      `/agents/${cluster}/gpu-monitor/alerts?status=${encodeURIComponent(status)}`
    )
  }

  return {
    overviewRealtime,
    overviewHistory,
    jobs,
    jobsAll,
    job,
    nodes,
    node,
    users,
    alerts
  }
}

export function useGpuMonitorPoller<ResponseType>(
  fetcher: () => Promise<ResponseType>,
  timeout: number
): GpuMonitorPoller<ResponseType> {
  const data: Ref<ResponseType | undefined> = ref()
  const unable: Ref<boolean> = ref(false)
  const loaded: Ref<boolean> = ref(false)
  const error: Ref<Error | undefined> = ref()
  const runtime = useRuntimeStore()
  let stopped = false
  let requestId = 0
  let timer = -1

  async function refresh() {
    const currentRequestId = ++requestId

    try {
      unable.value = false
      error.value = undefined
      data.value = await fetcher()
      if (stopped || currentRequestId !== requestId) {
        return
      }
      loaded.value = true
    } catch (fetchError) {
      if (stopped || currentRequestId !== requestId || !(fetchError instanceof Error)) {
        return
      }
      unable.value = true
      error.value = fetchError
      runtime.reportError(`GPU monitor error: ${fetchError.message}`)
    }
  }

  async function start() {
    stopped = false
    await refresh()
    if (!stopped) {
      timer = window.setTimeout(start, timeout)
    }
  }

  function stop() {
    stopped = true
    requestId += 1
    clearTimeout(timer)
  }

  async function restart() {
    stop()
    loaded.value = false
    await start()
  }

  onMounted(() => {
    start()
  })
  onUnmounted(() => {
    stop()
  })

  return { data, unable, loaded, error, refresh, restart }
}
