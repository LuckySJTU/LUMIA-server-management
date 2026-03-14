<!--
  Copyright (c) 2023-2024 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'
import { Chart } from 'chart.js/auto'
import type { ChartConfiguration } from 'chart.js'
import 'chartjs-adapter-luxon'
import { useRuntimeStore } from '@/stores/runtime'
import ClusterMainLayout from '@/components/ClusterMainLayout.vue'
import { useClusterDataPoller } from '@/composables/DataPoller'
import type { ClusterDataPoller } from '@/composables/DataPoller'
import { getMBHumanUnit, getNodeGPU, getNodeGPUFromGres } from '@/composables/GatewayAPI'
import type { ClusterIndividualNode, ClusterJob, ClusterNode } from '@/composables/GatewayAPI'
import {
  averageGpuMetric,
  formatGpuPercent,
  useGpuMonitorAPI,
  useGpuMonitorPoller
} from '@/composables/GpuMonitorAPI'
import type {
  GpuMonitorDetailRange,
  GpuMonitorNodeDetail,
  GpuMonitorNodeSeriesAggregatePoint,
  GpuMonitorNodeSeriesRealtimePoint
} from '@/composables/GpuMonitorAPI'
import NodeMainState from '@/components/resources/NodeMainState.vue'
import NodeAllocationState from '@/components/resources/NodeAllocationState.vue'
import JobStatusBadge from '@/components/job/JobStatusBadge.vue'
import ErrorAlert from '@/components/ErrorAlert.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import { ChevronLeftIcon } from '@heroicons/vue/20/solid'

const { cluster, nodeName } = defineProps<{ cluster: string; nodeName: string }>()

const runtimeStore = useRuntimeStore()
const router = useRouter()
const gpuMonitorAPI = useGpuMonitorAPI()
const gpuMonitorRange = ref<GpuMonitorDetailRange>('1d')
const gpuUtilCanvas = useTemplateRef<HTMLCanvasElement>('gpuUtilCanvas')
const memUtilCanvas = useTemplateRef<HTMLCanvasElement>('memUtilCanvas')
let gpuUtilChart: Chart | null = null
let memUtilChart: Chart | null = null

function backToResources() {
  router.push({
    name: 'resources',
    params: { cluster: runtimeStore.currentCluster?.name },
    query: runtimeStore.resources.query() as LocationQueryRaw
  })
}

const node = useClusterDataPoller<ClusterIndividualNode>(cluster, 'node', 5000, nodeName)
const nodes = useClusterDataPoller<ClusterNode[]>(cluster, 'nodes', 10000)
const gpuNode = useGpuMonitorPoller<GpuMonitorNodeDetail>(
  () => gpuMonitorAPI.node(cluster, nodeName, gpuMonitorRange.value),
  15000
)
const gpuNodeData = computed(() => gpuNode.data.value)
const gpuNodeSortedSeries = computed(() => {
  if (!gpuNodeData.value) return []
  return [...gpuNodeData.value.series].sort((a, b) => a.ts.localeCompare(b.ts))
})

function latestNodeSnapshot(): GpuMonitorNodeSeriesRealtimePoint[] {
  if (!gpuNodeData.value || gpuNodeData.value.range !== '1d' || !gpuNodeSortedSeries.value.length) {
    return []
  }
  const latestTimestamp = gpuNodeSortedSeries.value[gpuNodeSortedSeries.value.length - 1].ts
  return gpuNodeSortedSeries.value.filter(
    (point): point is GpuMonitorNodeSeriesRealtimePoint => point.ts === latestTimestamp
  )
}

function latestNodeAggregatePoint(): GpuMonitorNodeSeriesAggregatePoint | null {
  if (!gpuNodeData.value || gpuNodeData.value.range !== '1w' || !gpuNodeSortedSeries.value.length) {
    return null
  }
  return gpuNodeSortedSeries.value[gpuNodeSortedSeries.value.length - 1] as GpuMonitorNodeSeriesAggregatePoint
}

/* Poll jobs on current nodes if user has permission on view-jobs action. */
let jobs: ClusterDataPoller<ClusterJob[]> | undefined
if (runtimeStore.hasPermission('view-jobs')) {
  jobs = useClusterDataPoller<ClusterJob[]>(cluster, 'jobs', 10000, nodeName)
}

const gpuAvailable = computed(() => {
  if (!node.data.value) return 0
  return getNodeGPUFromGres(node.data.value.gres).reduce((gpu, current) => gpu + current.count, 0)
})

const gpuAllocated = computed(() => {
  if (!node.data.value) return 0
  return getNodeGPUFromGres(node.data.value.gres_used).reduce(
    (gpu, current) => gpu + current.count,
    0
  )
})

const displayPartitions = computed(() => {
  const nodeFromList = nodes.data.value?.find((currentNode) => currentNode.name === nodeName)
  if (nodeFromList?.partitions?.length) {
    return nodeFromList.partitions
  }
  return node.data.value?.partitions ?? []
})

const gpuNodeRealtimeSeries = computed((): GpuMonitorNodeSeriesRealtimePoint[] => {
  if (!gpuNodeData.value || gpuNodeData.value.range !== '1d') return []
  return gpuNodeSortedSeries.value as GpuMonitorNodeSeriesRealtimePoint[]
})

const gpuNodeAggregateSeries = computed((): GpuMonitorNodeSeriesAggregatePoint[] => {
  if (!gpuNodeData.value || gpuNodeData.value.range !== '1w') return []
  return gpuNodeSortedSeries.value as GpuMonitorNodeSeriesAggregatePoint[]
})

const gpuNodeTimeline = computed(() => {
  if (!gpuNodeData.value) return []

  if (gpuNodeData.value.range === '1d') {
    const grouped = new Map<
      string,
      { ts: string; gpuUtilValues: number[]; memUtilValues: number[]; gpuCount: number }
    >()
    for (const point of gpuNodeRealtimeSeries.value) {
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

  return gpuNodeAggregateSeries.value.map((point) => ({
    ts: point.ts,
    gpuUtil: point.avg_gpu_util_percent,
    memUtil: point.avg_mem_util_percent,
    gpuCount: point.allocated_gpu_count
  }))
})

function setGpuMonitorRange(range: GpuMonitorDetailRange) {
  gpuMonitorRange.value = range
}

function gpuNodeUnavailableMessage(): string {
  if (gpuNode.error.value instanceof Error && 'status' in gpuNode.error.value) {
    const error = gpuNode.error.value as { status: number }
    if (error.status === 404) {
      return 'No GPU metrics available for this node yet.'
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
  const timeline = gpuNodeTimeline.value.map((point) => ({
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

watch(
  () => cluster,
  (new_cluster) => {
    node.setCluster(new_cluster)
    nodes.setCluster(new_cluster)
    if (jobs) {
      jobs.setCluster(new_cluster)
    }
    gpuNode.restart()
  }
)

watch(
  () => nodeName,
  () => {
    gpuNode.restart()
  }
)

watch(gpuMonitorRange, () => {
  gpuNode.restart()
})

watch(
  () => gpuNodeTimeline.value,
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
})

onUnmounted(() => {
  gpuUtilChart?.destroy()
  memUtilChart?.destroy()
})
</script>

<template>
  <ClusterMainLayout
    menu-entry="resources"
    :cluster="cluster"
    :breadcrumb="[{ title: 'Resources', routeName: 'resources' }, { title: `Node ${nodeName}` }]"
  >
    <button
      @click="backToResources()"
      type="button"
      class="bg-slurmweb dark:bg-slurmweb-verydark hover:bg-slurmweb-dark focus-visible:outline-slurmweb-dark mt-8 mb-16 inline-flex items-center gap-x-2 rounded-md px-3.5 py-2.5 text-sm font-semibold text-white shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      <ChevronLeftIcon class="-ml-0.5 h-5 w-5" aria-hidden="true" />
      Back to resources
    </button>
    <ErrorAlert v-if="node.unable.value"
      >Unable to retrieve node {{ nodeName }} from cluster
      <span class="font-medium">{{ cluster }}</span></ErrorAlert
    >
    <div v-else-if="!node.loaded" class="text-gray-400 sm:pl-6 lg:pl-8">
      <LoadingSpinner :size="5" />
      Loading node {{ nodeName }}
    </div>
    <div v-else-if="node.data.value">
      <div class="flex justify-between">
        <div class="px-4 pb-8 sm:px-0">
          <h3 class="text-base leading-7 font-semibold text-gray-900 dark:text-gray-100">
            Node {{ nodeName }}
          </h3>
          <p class="mt-1 max-w-2xl text-sm leading-6 text-gray-500 dark:text-gray-300">
            All node statuses
          </p>
        </div>
      </div>
      <div class="flex flex-wrap">
        <div class="w-full">
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

            <div v-if="!gpuNode.loaded && !gpuNodeData" class="mt-4 text-gray-400 dark:text-gray-500">
              <LoadingSpinner :size="4" />
              Loading GPU metrics…
            </div>
            <div v-else-if="gpuNodeData" class="mt-4">
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
              v-else-if="gpuNode.unable"
              class="mt-4 text-sm font-medium text-amber-600 dark:text-amber-400"
            >
              {{ gpuNodeUnavailableMessage() }}
            </p>
          </section>
          <div class="border-t border-gray-100 dark:border-gray-700">
            <dl class="divide-y divide-gray-100 dark:divide-gray-700">
              <div id="status" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Node status
                </dt>
                <dd class="mt-1 text-sm leading-6 sm:col-span-2 sm:mt-0">
                  <NodeMainState :status="node.data.value.state" />
                  <span v-if="node.data.value.reason" class="pl-4 text-gray-500"
                    >reason: {{ node.data.value.reason }}</span
                  >
                </dd>
              </div>
              <div id="allocation" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Allocation status
                </dt>
                <dd
                  class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  <NodeAllocationState :status="node.data.value.state" />
                  <ul class="list-disc pt-4 pl-4">
                    <li>
                      CPU: {{ node.data.value.alloc_cpus }} / {{ node.data.value.cpus }}
                      <span class="text-gray-400 italic dark:text-gray-500"
                        >({{ (node.data.value.alloc_cpus / node.data.value.cpus) * 100 }}%)</span
                      >
                    </li>
                    <li>
                      Memory: {{ getMBHumanUnit(node.data.value.alloc_memory) }} /
                      {{ getMBHumanUnit(node.data.value.real_memory) }}
                      <span class="text-gray-400 italic dark:text-gray-600"
                        >({{
                          (node.data.value.alloc_memory / node.data.value.real_memory) * 100
                        }}%)</span
                      >
                    </li>
                    <li v-if="node.data.value.gres_used">
                      GPU: {{ gpuAllocated }} / {{ gpuAvailable }}
                      <span class="text-gray-400 italic dark:text-gray-600"
                        >({{ (gpuAllocated / gpuAvailable) * 100 }}%)</span
                      >
                    </li>
                  </ul>
                </dd>
              </div>
              <div v-if="jobs" id="jobs" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Current Jobs
                  <span
                    v-if="jobs.data.value"
                    class="text-slurmweb dark:text-slurmweb-light dark:bg-slurmweb-verydark ml-1 hidden rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium md:inline-block"
                    >{{ jobs.data.value.length }}</span
                  >
                </dt>
                <dd class="text-sm leading-6 sm:col-span-2">
                  <template v-if="jobs.data.value">
                    <ul v-if="jobs.data.value.length">
                      <li v-for="job in jobs.data.value" :key="job.job_id" class="inline">
                        <RouterLink
                          :to="{ name: 'job', params: { cluster: cluster, id: job.job_id } }"
                        >
                          <JobStatusBadge
                            :status="job.job_state"
                            :label="job.job_id.toString()"
                            class="mr-1"
                          />
                        </RouterLink>
                      </li>
                    </ul>
                    <span v-else class="text-gray-400 dark:text-gray-600">∅</span>
                  </template>
                </dd>
              </div>
              <div id="cpu" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  CPU (socket x cores/socket)
                </dt>
                <dd
                  class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  {{ node.data.value.sockets }} x {{ node.data.value.cores }} =
                  {{ node.data.value.cpus }}
                </dd>
              </div>
              <div id="threads" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Threads/core
                </dt>
                <dd
                  class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  {{ node.data.value.threads }}
                </dd>
              </div>
              <div id="arch" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Architecture
                </dt>
                <dd
                  class="mt-1 font-mono text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  {{ node.data.value.architecture }}
                </dd>
              </div>
              <div id="memory" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Memory
                </dt>
                <dd
                  class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  {{ getMBHumanUnit(node.data.value.real_memory) }}
                </dd>
              </div>
              <div
                v-if="node.data.value.gres"
                id="memory"
                class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0"
              >
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">GPU</dt>
                <dd
                  class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  <ul class="list-disc pl-4">
                    <li v-for="gpu in getNodeGPU(node.data.value.gres)" :key="gpu">{{ gpu }}</li>
                  </ul>
                </dd>
              </div>
              <div id="partitions" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Partitions
                </dt>
                <dd class="mt-1 text-sm leading-6 sm:col-span-2 sm:mt-0">
                  <span
                    v-for="partition in displayPartitions"
                    :key="partition"
                    class="rounded-sm bg-gray-500 px-2 py-1 font-medium text-white"
                    >{{ partition }}</span
                  >
                </dd>
              </div>
              <div id="kernel" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  OS Kernel
                </dt>
                <dd
                  class="mt-1 font-mono text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  {{ node.data.value.operating_system }}
                </dd>
              </div>
              <div id="reboot" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Reboot
                </dt>
                <dd
                  class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  <template v-if="node.data.value.boot_time.set">
                    {{ new Date(node.data.value.boot_time.number * 10 ** 3).toLocaleString() }}
                  </template>
                  <template v-else>N/A</template>
                </dd>
              </div>
              <div id="last" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                <dt class="text-sm leading-6 font-medium text-gray-900 dark:text-gray-100">
                  Last busy
                </dt>
                <dd
                  class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300"
                >
                  <template v-if="node.data.value.last_busy.set">
                    {{ new Date(node.data.value.last_busy.number * 10 ** 3).toLocaleString() }}
                  </template>
                  <template v-else>N/A</template>
                </dd>
              </div>
              <!--
                <div v-for="(value, property) in data" class="px-4 py-2 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-0">
                  <dt class="text-sm font-medium leading-6 text-gray-900">{{  property }}</dt>
                  <dd class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0"> {{ value }}</dd>
                </div>
              -->
            </dl>
          </div>
        </div>
      </div>
    </div>
  </ClusterMainLayout>
</template>
