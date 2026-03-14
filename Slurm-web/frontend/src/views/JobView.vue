<!--
  Copyright (c) 2023-2024 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import type { Component } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'
import { Chart } from 'chart.js/auto'
import type { ChartConfiguration } from 'chart.js'
import 'chartjs-adapter-luxon'
import ClusterMainLayout from '@/components/ClusterMainLayout.vue'
import { useClusterDataPoller } from '@/composables/DataPoller'
import { jobRequestedGPU, jobAllocatedGPU, useGatewayAPI } from '@/composables/GatewayAPI'
import type { ClusterIndividualJob } from '@/composables/GatewayAPI'
import {
  averageGpuMetric,
  formatGpuPercent,
  useGpuMonitorAPI,
  useGpuMonitorPoller
} from '@/composables/GpuMonitorAPI'
import type {
  GpuMonitorDetailRange,
  GpuMonitorJobDetail,
  GpuMonitorJobSeriesAggregatePoint,
  GpuMonitorJobSeriesRealtimePoint
} from '@/composables/GpuMonitorAPI'
import { buildSubmitPayloadFromJob } from '@/composables/jobCopy'
import JobStatusBadge from '@/components/job/JobStatusBadge.vue'
import JobProgress from '@/components/job/JobProgress.vue'
import { useRuntimeStore } from '@/stores/runtime'
import { useAuthStore } from '@/stores/auth'
import ErrorAlert from '@/components/ErrorAlert.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { ChevronLeftIcon } from '@heroicons/vue/20/solid'
import { HashtagIcon } from '@heroicons/vue/24/outline'
import JobFieldRaw from '@/components/job/JobFieldRaw.vue'
import JobFieldComment from '@/components/job/JobFieldComment.vue'
import JobFieldExitCode from '@/components/job/JobFieldExitCode.vue'
import JobResources from '@/components/job/JobResources.vue'

const { cluster, id } = defineProps<{ cluster: string; id: number }>()

const runtimeStore = useRuntimeStore()
const authStore = useAuthStore()
const gatewayAPI = useGatewayAPI()
const gpuMonitorAPI = useGpuMonitorAPI()
const router = useRouter()
const route = useRoute()
const cancelConfirmOpen = ref(false)
const canceling = ref(false)
const cancelError = ref('')
const copying = ref(false)
const copyError = ref('')
const gpuMonitorRange = ref<GpuMonitorDetailRange>('1d')
const gpuUtilCanvas = useTemplateRef<HTMLCanvasElement>('gpuUtilCanvas')
const memUtilCanvas = useTemplateRef<HTMLCanvasElement>('memUtilCanvas')
let gpuUtilChart: Chart | null = null
let memUtilChart: Chart | null = null

function backToJobs() {
  router.push({
    name: 'jobs',
    params: { cluster: runtimeStore.currentCluster?.name },
    query: runtimeStore.jobs.query() as LocationQueryRaw
  })
}

const JobsFields = [
  'name',
  'user',
  'account',
  'partition',
  'nodes',
  'qos',
  'priority',
  'comments',
  'workdir',
  'submit-line',
  'script',
  'exit-code',
  'tres-requested',
  'tres-allocated',
  'outputs',
  'errors'
] as const
type JobField = (typeof JobsFields)[number]

function isValidJobField(key: string): key is JobField {
  return typeof key === 'string' && JobsFields.includes(key as JobField)
}

const { data, unable, loaded, setCluster } = useClusterDataPoller<ClusterIndividualJob>(
  cluster,
  'job',
  5000,
  id
)
const gpuJob = useGpuMonitorPoller<GpuMonitorJobDetail>(
  () => gpuMonitorAPI.job(cluster, id, gpuMonitorRange.value),
  15000
)
const gpuJobData = computed(() => gpuJob.data.value)
const gpuJobSortedSeries = computed(() => {
  if (!gpuJobData.value) return []
  return [...gpuJobData.value.series].sort((a, b) => a.ts.localeCompare(b.ts))
})

function latestJobSnapshot(): GpuMonitorJobSeriesRealtimePoint[] {
  if (!gpuJobData.value || gpuJobData.value.range !== '1d' || !gpuJobSortedSeries.value.length) {
    return []
  }
  const latestTimestamp = gpuJobSortedSeries.value[gpuJobSortedSeries.value.length - 1].ts
  return gpuJobSortedSeries.value.filter(
    (point): point is GpuMonitorJobSeriesRealtimePoint => point.ts === latestTimestamp
  )
}

function latestJobAggregatePoint(): GpuMonitorJobSeriesAggregatePoint | null {
  if (!gpuJobData.value || gpuJobData.value.range !== '1w' || !gpuJobSortedSeries.value.length) {
    return null
  }
  return gpuJobSortedSeries.value[gpuJobSortedSeries.value.length - 1] as GpuMonitorJobSeriesAggregatePoint
}

const gpuJobCoverage = computed(() => {
  if (!gpuJobData.value) return null
  if (gpuJobData.value.range === '1d') {
    return {
      userName: gpuJobData.value.user_name,
      nodes: gpuJobData.value.nodes,
      gpus: gpuJobData.value.gpus
    }
  }
  return {
    userName: undefined,
    nodes: [],
    gpus: []
  }
})

const gpuJobRealtimeSeries = computed((): GpuMonitorJobSeriesRealtimePoint[] => {
  if (!gpuJobData.value || gpuJobData.value.range !== '1d') return []
  return gpuJobSortedSeries.value as GpuMonitorJobSeriesRealtimePoint[]
})

const gpuJobAggregateSeries = computed((): GpuMonitorJobSeriesAggregatePoint[] => {
  if (!gpuJobData.value || gpuJobData.value.range !== '1w') return []
  return gpuJobSortedSeries.value as GpuMonitorJobSeriesAggregatePoint[]
})

const gpuJobTimeline = computed(() => {
  if (!gpuJobData.value) return []

  if (gpuJobData.value.range === '1d') {
    const grouped = new Map<
      string,
      { ts: string; gpuUtilValues: number[]; memUtilValues: number[]; gpuCount: number }
    >()
    for (const point of gpuJobRealtimeSeries.value) {
      const entry = grouped.get(point.ts) || {
        ts: point.ts,
        gpuUtilValues: [],
        memUtilValues: [],
        gpuCount: 0
      }
      entry.gpuUtilValues.push(point.gpu_util_percent)
      entry.memUtilValues.push(point.mem_util_percent)
      entry.gpuCount += 1
      grouped.set(point.ts, entry)
    }
    return [...grouped.values()].map((entry) => ({
      ts: entry.ts,
      gpuUtil: averageGpuMetric(entry.gpuUtilValues) ?? 0,
      memUtil: averageGpuMetric(entry.memUtilValues) ?? 0,
      gpuCount: entry.gpuCount
    }))
  }

  return gpuJobAggregateSeries.value.map((point) => ({
    ts: point.ts,
    gpuUtil: point.avg_gpu_util_percent,
    memUtil: point.avg_mem_util_percent,
    gpuCount: point.gpu_count
  }))
})

const displayTags = ref<Record<JobField, { show: boolean; highlight: boolean }>>({
  user: { show: false, highlight: false },
  account: { show: false, highlight: false },
  name: { show: false, highlight: false },
  partition: { show: false, highlight: false },
  nodes: { show: false, highlight: false },
  qos: { show: false, highlight: false },
  priority: { show: false, highlight: false },
  comments: { show: false, highlight: false },
  workdir: { show: false, highlight: false },
  'submit-line': { show: false, highlight: false },
  script: { show: false, highlight: false },
  'exit-code': { show: false, highlight: false },
  'tres-requested': { show: false, highlight: false },
  'tres-allocated': { show: false, highlight: false },
  outputs: { show: false, highlight: false },
  errors: { show: false, highlight: false }
})

const jobFieldsContent = computed(
  (): { id: JobField; label: string; component: Component; props: object }[] => {
    if (!data.value) return []
    const preferredScript = data.value.command || data.value.script
    const scriptContent =
      preferredScript && preferredScript !== 'NONE' ? preferredScript : ''
    const scriptLineCount = scriptContent.length ? scriptContent.split('\n').length : 0
    const hasScriptContent = scriptContent.trim().length > 0
    const scriptScrollable = scriptLineCount > 10
    const showExitCode =
      !data.value.state.current.includes('PENDING') &&
      !data.value.state.current.includes('RUNNING')
    return [
      { id: 'name', label: 'Name', component: JobFieldRaw, props: { field: data.value.name } },
      { id: 'user', label: 'User', component: JobFieldRaw, props: { field: data.value.user } },
      {
        id: 'account',
        label: 'Account',
        component: JobFieldRaw,
        props: { field: data.value.association.account }
      },
      {
        id: 'partition',
        label: 'Partition',
        component: JobFieldRaw,
        props: { field: data.value.partition }
      },
      { id: 'nodes', label: 'Nodes', component: JobFieldRaw, props: { field: data.value.nodes } },
      { id: 'qos', label: 'QOS', component: JobFieldRaw, props: { field: data.value.qos } },
      {
        id: 'priority',
        label: 'Priority',
        component: JobFieldRaw,
        props: { field: data.value.priority.number }
      },
      {
        id: 'comments',
        label: 'Comments',
        component: JobFieldComment,
        props: { comment: data.value.comment }
      },
      {
        id: 'workdir',
        label: 'Working directory',
        component: JobFieldRaw,
        props: { field: data.value.working_directory, monospace: true }
      },
      {
        id: 'submit-line',
        label: 'Submit line',
        component: JobFieldRaw,
        props: { field: data.value.submit_line, monospace: true }
      },
      ...(hasScriptContent
        ? [
            {
              id: 'script' as JobField,
              label: 'Script',
              component: JobFieldRaw,
              props: {
                field: scriptContent,
                monospace: true,
                preserveLines: true,
                scrollable: scriptScrollable
              }
            }
          ]
        : []),
      ...(showExitCode
        ? [
            {
              id: 'exit-code' as JobField,
              label: 'Exit Code',
              component: JobFieldExitCode,
              props: { exit_code: data.value.exit_code }
            }
          ]
        : []),
      {
        id: 'tres-requested',
        label: 'Requested',
        component: JobResources,
        props: { tres: data.value.tres.requested, gpu: jobRequestedGPU(data.value) }
      },
      {
        id: 'tres-allocated',
        label: 'Allocated',
        component: JobResources,
        props: {
          tres: data.value.tres.allocated,
          gpu: { count: jobAllocatedGPU(data.value), reliable: true }
        }
      },
      {
        id: 'outputs',
        label: 'Outputs',
        component: JobFieldRaw,
        props: { field: data.value.standard_output === 'NONE' ? '' : data.value.standard_output, monospace: true }
      },
      {
        id: 'errors',
        label: 'Errors',
        component: JobFieldRaw,
        props: { field: data.value.standard_error === 'NONE' ? '' : data.value.standard_error, monospace: true }
      }
    ]
  }
)

const canCancel = computed(() => {
  if (!data.value) return false
  const canCancelOwnJob = runtimeStore.hasPermission('cancel-job')
  const canCancelAllJobs = runtimeStore.hasPermission('cancel-all-job')
  if (!canCancelOwnJob && !canCancelAllJobs) return false
  const isOwner = authStore.username && data.value.user === authStore.username
  const states = data.value.state.current
  const isActive = states.includes('PENDING') || states.includes('RUNNING')
  if (!isActive) return false
  return Boolean((canCancelOwnJob && isOwner) || canCancelAllJobs)
})

const canCopy = computed(() => {
  if (!data.value) return false
  if (!runtimeStore.hasPermission('submit-job')) return false
  if (data.value.node_count && data.value.node_count.set) {
    return data.value.node_count.number <= 1
  }
  return true
})

const gpuJobSummary = computed(() => {
  if (!gpuJobData.value) return null

  if (gpuJobData.value.range === '1d') {
    const latestSnapshot = latestJobSnapshot()
    return {
      gpuCount: new Set(latestSnapshot.map((point) => point.gpu_uuid)).size,
      nodeCount: new Set(latestSnapshot.map((point) => point.node_name)).size,
      sampleCount: gpuJobData.value.series.length,
      avgGpuUtil: averageGpuMetric(latestSnapshot.map((point) => point.gpu_util_percent)),
      avgMemUtil: averageGpuMetric(latestSnapshot.map((point) => point.mem_util_percent)),
      latestTimestamp: latestSnapshot[0]?.ts,
      peakGpuUtil: averageGpuMetric(gpuJobRealtimeSeries.value.map((point) => point.gpu_util_percent))
    }
  }

  const latestPoint = latestJobAggregatePoint()
  return {
    gpuCount: latestPoint?.gpu_count ?? 0,
    nodeCount: undefined,
    sampleCount: gpuJobData.value.series.length,
    avgGpuUtil: latestPoint?.avg_gpu_util_percent ?? null,
    avgMemUtil: latestPoint?.avg_mem_util_percent ?? null,
    latestTimestamp: latestPoint?.ts,
    peakGpuUtil: Math.max(...gpuJobAggregateSeries.value.map((point) => point.avg_gpu_util_percent), 0)
  }
})

const gpuJobSeries = computed(() => {
  return [...gpuJobSortedSeries.value].slice(-8).reverse()
})

const recentGpuJobRealtimeSeries = computed(() => {
  return [...gpuJobRealtimeSeries.value].slice(-8).reverse()
})

const recentGpuJobAggregateSeries = computed(() => {
  return [...gpuJobAggregateSeries.value].slice(-8).reverse()
})

function setGpuMonitorRange(range: GpuMonitorDetailRange) {
  gpuMonitorRange.value = range
}

function gpuJobUnavailableMessage(): string {
  if (gpuJob.error.value instanceof Error && 'status' in gpuJob.error.value) {
    const error = gpuJob.error.value as { status: number }
    if (error.status === 404) {
      return 'No GPU metrics available for this job yet.'
    }
  }
  return 'GPU monitor data is temporarily unavailable.'
}

function chartOptions(label: string): ChartConfiguration<'line'>['options'] {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false
    },
    plugins: {
      title: {
        display: true,
        text: label
      },
      legend: {
        display: false
      },
      tooltip: {
        callbacks: {
          label(context) {
            return `${label}: ${Number((context.raw as { y: number }).y).toFixed(1)}%`
          }
        }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 100,
        ticks: {
          callback(value) {
            return `${value}%`
          }
        }
      },
      x: {
        type: 'time',
        time: {
          unit: gpuMonitorRange.value === '1d' ? 'hour' : 'day'
        },
        ticks: {
          autoSkip: false,
          maxRotation: gpuMonitorRange.value === '1w' ? 0 : 50,
          minRotation: gpuMonitorRange.value === '1w' ? 0 : 0
        }
      }
    }
  }
}

function ensureCharts() {
  if (gpuUtilCanvas.value && !gpuUtilChart) {
    gpuUtilChart = new Chart(gpuUtilCanvas.value, {
      type: 'line',
      data: { datasets: [] },
      options: chartOptions('GPU Utilization')
    })
  }
  if (memUtilCanvas.value && !memUtilChart) {
    memUtilChart = new Chart(memUtilCanvas.value, {
      type: 'line',
      data: { datasets: [] },
      options: chartOptions('Memory Utilization')
    })
  }
}

function updateCharts() {
  ensureCharts()
  const timeline = gpuJobTimeline.value.map((point) => ({
    x: new Date(point.ts).getTime(),
    gpuUtil: point.gpuUtil,
    memUtil: point.memUtil
  }))

  if (gpuUtilChart) {
    gpuUtilChart.data.datasets = [
      {
        label: 'GPU Utilization',
        data: timeline.map((point) => ({ x: point.x, y: point.gpuUtil })),
        borderColor: 'rgb(26, 86, 219)',
        backgroundColor: 'rgba(26, 86, 219, 0.18)',
        tension: 0.28,
        fill: true,
        pointRadius: gpuMonitorRange.value === '1d' ? 2 : 3
      }
    ]
    gpuUtilChart.options = chartOptions('GPU Utilization') || {}
    gpuUtilChart.update()
  }

  if (memUtilChart) {
    memUtilChart.data.datasets = [
      {
        label: 'Memory Utilization',
        data: timeline.map((point) => ({ x: point.x, y: point.memUtil })),
        borderColor: 'rgb(5, 150, 105)',
        backgroundColor: 'rgba(5, 150, 105, 0.18)',
        tension: 0.28,
        fill: true,
        pointRadius: gpuMonitorRange.value === '1d' ? 2 : 3
      }
    ]
    memUtilChart.options = chartOptions('Memory Utilization') || {}
    memUtilChart.update()
  }
}

async function cancelJob() {
  cancelError.value = ''
  canceling.value = true
  try {
    if (runtimeStore.hasPermission('cancel-all-job')) {
      await gatewayAPI.cancelAll(cluster, id)
    } else {
      await gatewayAPI.cancel(cluster, id)
    }
    cancelConfirmOpen.value = false
  } catch (error) {
    cancelError.value = error instanceof Error ? error.message : String(error)
  } finally {
    canceling.value = false
  }
}

async function copyCurrentJob() {
  if (!data.value) return
  copyError.value = ''
  copying.value = true
  try {
    runtimeStore.setSubmitJobDraft(cluster, buildSubmitPayloadFromJob(data.value))
    router.push({ name: 'submit-job', params: { cluster } })
  } catch (error) {
    copyError.value = error instanceof Error ? error.message : String(error)
  } finally {
    copying.value = false
  }
}

/* highlight this field for some time */
function highlightField(field: JobField) {
  displayTags.value[field].highlight = true
  setTimeout(() => {
    displayTags.value[field].highlight = false
  }, 2000)
}

watch(
  () => cluster,
  (new_cluster) => {
    setCluster(new_cluster)
    gpuJob.restart()
  }
)

watch(
  () => id,
  () => {
    gpuJob.restart()
  }
)

watch(gpuMonitorRange, () => {
  gpuJob.restart()
})

watch(
  () => gpuJobTimeline.value,
  () => {
    updateCharts()
  }
)

watch(
  [() => gpuUtilCanvas.value, () => memUtilCanvas.value],
  () => {
    ensureCharts()
    updateCharts()
  }
)

onMounted(() => {
  ensureCharts()
  updateCharts()
  /* If a job field is in route hash, highlight this field. */
  if (route.hash) {
    const field = route.hash.slice(1) // remove initial hash
    if (isValidJobField(field)) {
      highlightField(field)
    }
  }
})

onUnmounted(() => {
  gpuUtilChart?.destroy()
  memUtilChart?.destroy()
})
</script>

<template>
  <ClusterMainLayout
    menu-entry="jobs"
    :cluster="cluster"
    :breadcrumb="[{ title: 'Jobs', routeName: 'jobs' }, { title: `Job ${id}` }]"
  >
    <button
      @click="backToJobs()"
      type="button"
      class="bg-slurmweb dark:bg-slurmweb-verydark hover:bg-slurmweb-dark focus-visible:outline-slurmweb-dark mt-8 mb-16 inline-flex items-center gap-x-2 rounded-md px-3.5 py-2.5 text-sm font-semibold text-white shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      <ChevronLeftIcon class="-ml-0.5 h-5 w-5" aria-hidden="true" />
      Back to jobs
    </button>

    <ErrorAlert v-if="unable"
      >Unable to retrieve job {{ id }} from cluster
      <span class="font-medium">{{ cluster }}</span></ErrorAlert
    >
    <div v-else-if="!loaded" class="text-gray-400 sm:pl-6 lg:pl-8">
      <LoadingSpinner :size="5" />
      Loading job {{ id }}
    </div>
    <div v-else-if="data">
      <div class="flex justify-between">
        <div class="px-4 pb-8 sm:px-0">
          <div class="flex items-start gap-6">
            <div>
              <h3 class="text-base leading-7 font-semibold text-gray-900 dark:text-gray-100">
                Job {{ id }}
              </h3>
              <p class="mt-1 max-w-2xl text-sm leading-6 text-gray-500 dark:text-gray-300">
                All job settings
              </p>
            </div>
            <div>
              <div class="flex items-center gap-3">
                <JobStatusBadge :status="data.state.current" :large="true" />
                <span v-if="data.state.reason != 'None'" class="text-gray-900 dark:text-gray-100">{{
                  data.state.reason
                }}</span>
              </div>
              <p v-if="copyError" class="mt-2 text-sm font-semibold text-red-600 dark:text-red-400">
                {{ copyError }}
              </p>
              <p v-if="cancelError" class="mt-2 text-sm font-semibold text-red-600 dark:text-red-400">
                {{ cancelError }}
              </p>
            </div>
          </div>
        </div>
        <div class="flex flex-col items-end gap-2">
          <div class="flex items-center gap-3">
            <button
              v-if="canCopy"
              type="button"
              class="bg-action-copy dark:bg-action-copy-dark hover:bg-action-copy-darker focus-visible:outline-action-copy inline-flex items-center rounded-md px-3 py-2 text-sm font-semibold text-white shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="copying"
              @click="copyCurrentJob"
            >
              {{ copying ? 'Copying…' : 'Copy' }}
            </button>
            <button
              v-if="canCancel"
              type="button"
              class="bg-action-cancel dark:bg-action-cancel-dark hover:bg-action-cancel-darker focus-visible:outline-action-cancel inline-flex items-center rounded-md px-3 py-2 text-sm font-semibold text-white shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
              @click="cancelConfirmOpen = true"
            >
              Cancel Job
            </button>
          </div>
        </div>
      </div>
      <section class="mb-8 rounded-lg border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-700 dark:bg-gray-900">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <h4 class="text-base font-semibold text-gray-900 dark:text-gray-100">GPU Monitor</h4>
          <span class="isolate inline-flex rounded-md shadow-xs">
            <button
              type="button"
              :class="[
                gpuMonitorRange == '1w'
                  ? 'bg-slurmweb dark:bg-slurmweb-dark text-white'
                  : 'bg-white text-gray-900 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-200 hover:dark:bg-gray-700',
                'relative inline-flex items-center rounded-l-md px-3 py-2 text-xs font-semibold ring-1 ring-gray-300 ring-inset dark:ring-gray-600'
              ]"
              @click="setGpuMonitorRange('1w')"
            >
              1w
            </button>
            <button
              type="button"
              :class="[
                gpuMonitorRange == '1d'
                  ? 'bg-slurmweb dark:bg-slurmweb-dark text-white'
                  : 'bg-white text-gray-900 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-200 hover:dark:bg-gray-700',
                'relative inline-flex items-center rounded-r-md px-3 py-2 text-xs font-semibold ring-1 ring-gray-300 ring-inset dark:ring-gray-600'
              ]"
              @click="setGpuMonitorRange('1d')"
            >
              1d
            </button>
          </span>
        </div>

        <div v-if="!gpuJob.loaded && !gpuJobData" class="mt-4 text-gray-400 dark:text-gray-500">
          <LoadingSpinner :size="4" />
          Loading GPU metrics…
        </div>
        <div v-else-if="gpuJobData && gpuJobSummary" class="mt-4">
          <div class="grid gap-5 xl:grid-cols-2">
            <div class="rounded-xl border border-gray-200 p-5 dark:border-gray-700">
              <div class="h-72 w-full">
                <canvas ref="gpuUtilCanvas"></canvas>
              </div>
            </div>

            <div class="rounded-xl border border-gray-200 p-5 dark:border-gray-700">
              <div class="h-72 w-full">
                <canvas ref="memUtilCanvas"></canvas>
              </div>
            </div>
          </div>
        </div>
        <p
          v-else-if="gpuJob.unable"
          class="mt-4 text-sm font-medium text-amber-600 dark:text-amber-400"
        >
          {{ gpuJobUnavailableMessage() }}
        </p>
      </section>
      <div class="flex flex-wrap">
        <div class="w-full lg:w-1/3">
          <JobProgress v-if="data" :job="data" />
        </div>
        <div class="w-full lg:w-2/3">
          <div class="border-t border-gray-100 dark:border-gray-700">
            <dl class="divide-y divide-gray-100 dark:divide-gray-700">
              <div
                v-for="field in jobFieldsContent"
                :key="field.id"
                :id="`${field.id}`"
                :class="[
                  displayTags[field.id].highlight ? 'bg-slurmweb-light dark:bg-slurmweb-dark' : '',
                  'px-4 py-2 transition-colors duration-700 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0'
                ]"
              >
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  <a :href="`#${field.id}`">
                    <span
                      class="flex items-center"
                      @mouseover="displayTags[field.id].show = true"
                      @mouseleave="displayTags[field.id].show = false"
                    >
                      <HashtagIcon
                        v-show="displayTags[field.id].show"
                        class="mr-2 -ml-5 h-3 w-3 text-gray-500"
                        aria-hidden="true"
                      />
                      {{ field.label }}
                    </span>
                  </a>
                </dt>
                <component :is="field.component" v-bind="field.props" />
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="cancelConfirmOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
    >
      <div class="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-slate-900">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Cancel job {{ id }}?</h3>
        <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
          This will stop the job if it is currently queued or running.
        </p>
        <div class="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            class="rounded-md border border-gray-300 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:text-gray-200 dark:hover:bg-slate-800"
            :disabled="canceling"
            @click="cancelConfirmOpen = false"
          >
            Back
          </button>
          <button
            type="button"
            class="bg-action-cancel dark:bg-action-cancel-dark hover:bg-action-cancel-darker focus-visible:outline-action-cancel rounded-md px-3 py-2 text-sm font-semibold text-white shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="canceling"
            @click="cancelJob"
          >
            <span v-if="canceling">Canceling…</span>
            <span v-else>Confirm Cancel</span>
          </button>
        </div>
      </div>
    </div>
  </ClusterMainLayout>
</template>
