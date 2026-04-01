<!--
  Copyright (c) 2023-2024 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
import { computed, onMounted, onUnmounted, useTemplateRef, watch } from 'vue'
import { Chart } from 'chart.js/auto'
import type { ChartConfiguration } from 'chart.js'
import 'chartjs-adapter-luxon'
import { getMBHumanUnit } from '@/composables/GatewayAPI'
import type { ClusterStats } from '@/composables/GatewayAPI'
import { formatGpuPercent, useGpuMonitorAPI, useGpuMonitorPoller } from '@/composables/GpuMonitorAPI'
import type {
  GpuMonitorAlertItem,
  GpuMonitorJobsListItem,
  GpuMonitorNodesListItem,
  GpuMonitorOverviewHistoryResponse,
  GpuMonitorOverviewRealtime,
  GpuMonitorUsersListItem
} from '@/composables/GpuMonitorAPI'
import { useRuntimeStore } from '@/stores/runtime'
import { useClusterDataPoller } from '@/composables/DataPoller'
import ClusterMainLayout from '@/components/ClusterMainLayout.vue'
import DashboardCharts from '@/components/dashboard/DashboardCharts.vue'
import ErrorAlert from '@/components/ErrorAlert.vue'

const runtimeStore = useRuntimeStore()

const { cluster } = defineProps<{ cluster: string }>()

const { data, unable, loaded, setCluster } = useClusterDataPoller<ClusterStats>(
  cluster,
  'stats',
  10000
)
const gpuMonitorAPI = useGpuMonitorAPI()
const gpuActivityHistoryCanvas = useTemplateRef<HTMLCanvasElement>('gpuActivityHistoryCanvas')
let gpuActivityHistoryChart: Chart | null = null
const gpuOverview = useGpuMonitorPoller<GpuMonitorOverviewRealtime>(
  () => gpuMonitorAPI.overviewRealtime(cluster),
  15000
)
const gpuOverviewHistory = useGpuMonitorPoller<GpuMonitorOverviewHistoryResponse>(
  () => gpuMonitorAPI.overviewHistory(cluster, '7d'),
  30000
)
const gpuAlerts = useGpuMonitorPoller<GpuMonitorAlertItem[]>(
  async () => (await gpuMonitorAPI.alerts(cluster, 'active')).items,
  15000
)
const gpuJobs = useGpuMonitorPoller<GpuMonitorJobsListItem[]>(
  () => gpuMonitorAPI.jobsAll(cluster, 'realtime'),
  15000
)
const gpuUsers = useGpuMonitorPoller<GpuMonitorUsersListItem[]>(
  async () => (await gpuMonitorAPI.users(cluster, 'realtime')).items,
  15000
)
const gpuNodes = useGpuMonitorPoller<GpuMonitorNodesListItem[]>(
  async () => (await gpuMonitorAPI.nodes(cluster, 'realtime')).items,
  15000
)
const gpuOverviewData = computed(() => gpuOverview.data.value)
const gpuOverviewHistoryData = computed(() => gpuOverviewHistory.data.value)
const maxAllocatedGpuAxis = computed(() => {
  const totalGpus = data.value?.resources.gpus
  return typeof totalGpus === 'number' && Number.isFinite(totalGpus) && totalGpus > 0
    ? totalGpus
    : undefined
})
const gpuOverviewLast24h = computed(() => {
  const series = [...(gpuOverviewHistoryData.value?.series || [])].sort((a, b) => a.ts.localeCompare(b.ts))
  if (!series.length) {
    return []
  }

  const latestTimestamp = Date.parse(series[series.length - 1].ts)
  if (Number.isNaN(latestTimestamp)) {
    return series
  }

  const cutoff = latestTimestamp - 24 * 60 * 60 * 1000
  return series.filter((point) => {
    const timestamp = Date.parse(point.ts)
    return !Number.isNaN(timestamp) && timestamp >= cutoff
  })
})
const gpuJobsById = computed(() => new Map((gpuJobs.data.value || []).map((item) => [item.job_id, item])))
const gpuUsersByName = computed(
  () => new Map((gpuUsers.data.value || []).map((item) => [item.user_name, item]))
)
const gpuNodesByName = computed(
  () => new Map((gpuNodes.data.value || []).map((item) => [item.node_name, item]))
)
const activeAlertsCards = computed(() => {
  const alerts = gpuAlerts.data.value || []
  const criticalJobIds = new Set(
    alerts
      .filter((alert) => alert.entity_type === 'job' && alert.level === 'critical')
      .map((alert) => alert.entity_id)
  )

  return alerts
    .filter((alert) => {
      return !(
        alert.entity_type === 'job' &&
        alert.level === 'warning' &&
        criticalJobIds.has(alert.entity_id)
      )
    })
    .map((alert) => {
    if (alert.entity_type === 'job') {
      const job = gpuJobsById.value.get(alert.entity_id)
      return {
        ...alert,
        tone:
          alert.level === 'critical'
            ? 'border-red-300 bg-red-50 text-red-900 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-100'
            : 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100',
        badge:
          alert.level === 'critical'
            ? 'bg-red-600 text-white dark:bg-red-700'
            : 'bg-amber-500 text-white dark:bg-amber-600',
        metaLabel: 'Job',
        title: `Job ${alert.entity_id}`,
        subtitle: job?.user_name || 'Unknown user',
        detail: job ? `${job.gpu_count} GPU` : '-'
      }
    }
    if (alert.entity_type === 'user') {
      const user = gpuUsersByName.value.get(alert.entity_id)
      return {
        ...alert,
        tone: 'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-100',
        badge: 'bg-amber-500 text-white dark:bg-amber-600',
        metaLabel: 'User',
        title: alert.entity_id,
        subtitle: 'Allocated GPUs',
        detail: user ? `${user.allocated_gpu_count}` : '-'
      }
    }
    const node = gpuNodesByName.value.get(alert.entity_id)
    return {
      ...alert,
      tone: 'border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-100',
      badge: 'bg-sky-600 text-white dark:bg-sky-700',
      metaLabel: 'Node',
      title: alert.entity_id,
      subtitle: 'Node name',
      detail: node?.node_name || alert.entity_id
    }
    })
})

function gpuActivityHistoryChartOptions(): ChartConfiguration<'line'>['options'] {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false
    },
    plugins: {
      legend: {
        position: 'top'
      },
      tooltip: {
        callbacks: {
          label(context) {
            const value = Number((context.raw as { y: number }).y)
            if (context.dataset.yAxisID === 'y1') {
              return `${context.dataset.label}: ${value.toFixed(1)}%`
            }
            return `${context.dataset.label}: ${value.toFixed(0)}`
          }
        }
      }
    },
    scales: {
      x: {
        type: 'time',
        time: {
          unit: 'hour'
        },
        ticks: {
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 8
        }
      },
      y: {
        position: 'left',
        beginAtZero: true,
        max: maxAllocatedGpuAxis.value,
        title: {
          display: true,
          text: 'Allocated GPUs'
        },
        ticks: {
          precision: 0
        }
      },
      y1: {
        position: 'right',
        beginAtZero: true,
        max: 100,
        grid: {
          drawOnChartArea: false
        },
        title: {
          display: true,
          text: 'Avg GPU Utilization (%)'
        },
        ticks: {
          callback(value) {
            return `${value}%`
          }
        }
      }
    }
  }
}

function ensureGpuActivityHistoryChart() {
  if (gpuActivityHistoryCanvas.value && !gpuActivityHistoryChart) {
    gpuActivityHistoryChart = new Chart(gpuActivityHistoryCanvas.value, {
      type: 'line',
      data: { datasets: [] },
      options: gpuActivityHistoryChartOptions()
    })
  }
}

function updateGpuActivityHistoryChart() {
  ensureGpuActivityHistoryChart()
  if (!gpuActivityHistoryChart) {
    return
  }

  const timeline = gpuOverviewLast24h.value.map((point) => ({
    x: new Date(point.ts).getTime(),
    allocatedGpuCount: point.allocated_gpu_count,
    avgGpuUtil: point.avg_gpu_util_percent
  }))

  gpuActivityHistoryChart.data.datasets = [
    {
      label: 'Allocated GPUs',
      data: timeline.map((point) => ({ x: point.x, y: point.allocatedGpuCount })),
      borderColor: 'rgb(37, 99, 235)',
      backgroundColor: 'rgba(37, 99, 235, 0.16)',
      yAxisID: 'y',
      cubicInterpolationMode: 'monotone',
      tension: 0.12,
      pointRadius: 0,
      pointHoverRadius: 3
    },
    {
      label: 'Avg GPU Utilization',
      data: timeline.map((point) => ({ x: point.x, y: point.avgGpuUtil })),
      borderColor: 'rgb(5, 150, 105)',
      backgroundColor: 'rgba(5, 150, 105, 0.16)',
      yAxisID: 'y1',
      cubicInterpolationMode: 'monotone',
      tension: 0.12,
      pointRadius: 0,
      pointHoverRadius: 3
    }
  ]
  gpuActivityHistoryChart.options = gpuActivityHistoryChartOptions() || {}
  gpuActivityHistoryChart.update()
}

watch(
  () => cluster,
  (new_cluster) => {
    setCluster(new_cluster)
    gpuOverview.restart()
    gpuOverviewHistory.restart()
    gpuAlerts.restart()
    gpuJobs.restart()
    gpuUsers.restart()
    gpuNodes.restart()
  }
)

watch(
  () => gpuOverviewLast24h.value,
  () => {
    updateGpuActivityHistoryChart()
  }
)

watch(
  () => maxAllocatedGpuAxis.value,
  () => {
    updateGpuActivityHistoryChart()
  }
)

watch(
  () => gpuActivityHistoryCanvas.value,
  () => {
    ensureGpuActivityHistoryChart()
    updateGpuActivityHistoryChart()
  }
)

onMounted(() => {
  ensureGpuActivityHistoryChart()
  updateGpuActivityHistoryChart()
})

onUnmounted(() => {
  gpuActivityHistoryChart?.destroy()
})
</script>

<template>
  <ClusterMainLayout
    menu-entry="dashboard"
    :cluster="cluster"
    :breadcrumb="[{ title: 'Dashboard' }]"
  >
    <div class="mx-auto max-w-7xl">
      <ErrorAlert v-if="unable"
        >Unable to retrieve statistics from cluster
        <span class="font-medium">{{ cluster }}</span></ErrorAlert
      >
      <div v-else class="mb-4 px-1">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Overview</h2>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">Total cluster resources</p>
      </div>
      <div
        class="grid grid-cols-2 gap-px bg-gray-200 md:grid-cols-3 xl:grid-cols-6 dark:bg-gray-700"
      >
        <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
          <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Nodes</p>
          <span
            v-if="loaded && data"
            id="metric-nodes"
            class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
          >
            {{ data.resources.nodes }}
          </span>
          <div v-else class="flex animate-pulse space-x-4">
            <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
          </div>
        </div>
        <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
          <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Cores</p>
          <span
            v-if="loaded && data"
            id="metric-cores"
            class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
          >
            {{ data.resources.cores }}
          </span>
          <div v-else class="flex animate-pulse space-x-4">
            <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
          </div>
        </div>
        <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
          <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Memory</p>
          <span
            v-if="loaded && data"
            id="metric-cores"
            class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
          >
            {{ getMBHumanUnit(data.resources.memory) }}
          </span>
          <div v-else class="flex animate-pulse space-x-4">
            <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
          </div>
        </div>
        <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
          <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">GPU</p>
          <span
            v-if="loaded && data"
            id="metric-cores"
            :class="[
              data.resources.gpus
                ? 'text-gray-600 dark:text-gray-500'
                : 'text-gray-200 dark:text-gray-700',
              'text-4xl font-semibold tracking-tight'
            ]"
          >
            {{ data.resources.gpus }}
          </span>
          <div v-else class="flex animate-pulse space-x-4">
            <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
          </div>
        </div>
        <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
          <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Running jobs</p>
          <span
            v-if="loaded && data"
            id="metric-jobs-running"
            class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
          >
            {{ data.jobs.running }}
          </span>
          <div v-else class="flex animate-pulse space-x-4">
            <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
          </div>
        </div>
        <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
          <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Total jobs</p>
          <span
            v-if="loaded && data"
            id="metric-jobs-total"
            class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
          >
            {{ data.jobs.total }}
          </span>
          <div v-else class="flex animate-pulse space-x-4">
            <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
          </div>
        </div>
      </div>
      <section class="mt-10">
        <div class="mb-4 flex items-center justify-between px-1">
          <div>
            <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">GPU Activity</h2>
            <p class="text-sm text-gray-500 dark:text-gray-300">
              Data updates may be delayed; please refer to actual usage.
            </p>
          </div>
        </div>
        <div
          class="grid grid-cols-2 gap-px bg-gray-200 md:grid-cols-3 xl:grid-cols-6 dark:bg-gray-700"
        >
          <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
            <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Tracked jobs</p>
            <span
              v-if="gpuOverview.loaded && gpuOverviewData"
              class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
            >
              {{ gpuOverviewData.running_job_count }}
            </span>
            <div v-else class="flex animate-pulse space-x-4">
              <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
            </div>
          </div>
          <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
            <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">
              Allocated GPUs
            </p>
            <span
              v-if="gpuOverview.loaded && gpuOverviewData"
              class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
            >
              {{ gpuOverviewData.allocated_gpu_count }}
            </span>
            <div v-else class="flex animate-pulse space-x-4">
              <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
            </div>
          </div>
          <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
            <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Avg GPU util</p>
            <span
              v-if="gpuOverview.loaded && gpuOverviewData"
              class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
            >
              {{ formatGpuPercent(gpuOverviewData.avg_gpu_util_percent) }}
            </span>
            <div v-else class="flex animate-pulse space-x-4">
              <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
            </div>
          </div>
          <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
            <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Avg mem util</p>
            <span
              v-if="gpuOverview.loaded && gpuOverviewData"
              class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
            >
              {{ formatGpuPercent(gpuOverviewData.avg_mem_util_percent) }}
            </span>
            <div v-else class="flex animate-pulse space-x-4">
              <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
            </div>
          </div>
          <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
            <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Low util jobs</p>
            <span
              v-if="gpuOverview.loaded && gpuOverviewData"
              class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
            >
              {{ gpuOverviewData.low_util_job_count }}
            </span>
            <div v-else class="flex animate-pulse space-x-4">
              <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
            </div>
          </div>
          <div class="bg-white px-4 py-6 sm:px-6 lg:px-8 dark:bg-gray-900">
            <p class="text-sm leading-6 font-medium text-gray-400 dark:text-gray-200">Active alerts</p>
            <span
              v-if="gpuOverview.loaded && gpuOverviewData"
              class="text-4xl font-semibold tracking-tight text-gray-600 dark:text-gray-500"
            >
              {{ gpuOverviewData.active_alert_count }}
            </span>
            <div v-else class="flex animate-pulse space-x-4">
              <div class="h-10 w-10 rounded-full bg-slate-200 dark:bg-slate-800"></div>
            </div>
          </div>
        </div>
        <div class="mt-6 rounded-xl border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
          <div class="mb-4">
            <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">Past 24 Hours</h3>
            <p class="text-sm text-gray-500 dark:text-gray-300">
              Allocated GPUs and average GPU utilization.
            </p>
          </div>
          <div
            v-if="gpuOverviewLast24h.length"
            class="h-80"
          >
            <canvas ref="gpuActivityHistoryCanvas"></canvas>
          </div>
          <div
            v-else-if="!gpuOverviewHistory.loaded"
            class="flex h-80 animate-pulse items-center justify-center rounded-lg bg-slate-50 dark:bg-slate-950/40"
          >
            <div class="h-24 w-full max-w-3xl rounded-lg bg-slate-200 dark:bg-slate-800"></div>
          </div>
          <div
            v-else
            class="flex h-80 items-center justify-center rounded-lg border border-dashed border-gray-300 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400"
          >
            No GPU activity history available yet.
          </div>
        </div>
      </section>
      <section class="mt-10">
        <div class="mb-4 px-1">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Active Alerts</h2>
          <p class="text-sm text-gray-500 dark:text-gray-300">
            Current GPU efficiency alerts by job, user, and node.
          </p>
        </div>
        <div v-if="activeAlertsCards.length" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="alert in activeAlertsCards"
            :key="alert.id"
            :class="['rounded-xl border p-5 shadow-xs', alert.tone]"
          >
            <div class="flex items-start justify-between gap-4">
              <div>
                <p class="text-xs font-medium tracking-[0.18em] uppercase opacity-75">
                  {{ alert.metaLabel }}
                </p>
                <h3 class="mt-1 text-lg font-semibold">{{ alert.title }}</h3>
              </div>
              <span :class="['rounded-full px-2.5 py-1 text-xs font-semibold uppercase', alert.badge]">
                {{ alert.level }}
              </span>
            </div>
            <div class="mt-4 space-y-2 text-sm">
              <p class="font-medium">{{ alert.summary }}</p>
              <div v-if="alert.entity_type === 'job'" class="flex items-center justify-between gap-4">
                <span class="opacity-75">User</span>
                <span class="font-semibold">{{ alert.subtitle }}</span>
              </div>
              <div v-if="alert.entity_type === 'job'" class="flex items-center justify-between gap-4">
                <span class="opacity-75">Allocated GPUs</span>
                <span class="font-semibold">{{ alert.detail }}</span>
              </div>
              <div v-if="alert.entity_type === 'user'" class="flex items-center justify-between gap-4">
                <span class="opacity-75">Allocated GPUs</span>
                <span class="font-semibold">{{ alert.detail }}</span>
              </div>
              <div v-if="alert.entity_type === 'node'" class="flex items-center justify-between gap-4">
                <span class="opacity-75">Node</span>
                <span class="font-semibold">{{ alert.detail }}</span>
              </div>
              <div class="flex items-center justify-between gap-4">
                <span class="opacity-75">Rule</span>
                <span class="font-semibold">{{ alert.rule_name }}</span>
              </div>
              <div class="flex items-center justify-between gap-4">
                <span class="opacity-75">Last seen</span>
                <span class="font-semibold">{{ new Date(alert.last_seen_time).toLocaleString() }}</span>
              </div>
            </div>
          </article>
        </div>
        <div
          v-else
          class="rounded-xl border border-dashed border-gray-300 px-5 py-8 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400"
        >
          No active GPU alerts.
        </div>
      </section>
      <DashboardCharts v-if="runtimeStore.getCluster(cluster).metrics" :cluster="cluster" />
    </div>
  </ClusterMainLayout>
</template>
