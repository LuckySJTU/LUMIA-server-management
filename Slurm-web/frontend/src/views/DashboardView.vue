<!--
  Copyright (c) 2023-2024 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
import { computed, watch } from 'vue'
import { getMBHumanUnit } from '@/composables/GatewayAPI'
import type { ClusterStats } from '@/composables/GatewayAPI'
import { formatGpuPercent, useGpuMonitorAPI, useGpuMonitorPoller } from '@/composables/GpuMonitorAPI'
import type {
  GpuMonitorAlertItem,
  GpuMonitorJobsListItem,
  GpuMonitorNodesListItem,
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
const gpuOverview = useGpuMonitorPoller<GpuMonitorOverviewRealtime>(
  () => gpuMonitorAPI.overviewRealtime(cluster),
  15000
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
const gpuJobsById = computed(() => new Map((gpuJobs.data.value || []).map((item) => [item.job_id, item])))
const gpuUsersByName = computed(
  () => new Map((gpuUsers.data.value || []).map((item) => [item.user_name, item]))
)
const gpuNodesByName = computed(
  () => new Map((gpuNodes.data.value || []).map((item) => [item.node_name, item]))
)
const activeAlertsCards = computed(() => {
  return (gpuAlerts.data.value || []).map((alert) => {
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

watch(
  () => cluster,
  (new_cluster) => {
    setCluster(new_cluster)
    gpuOverview.restart()
    gpuAlerts.restart()
    gpuJobs.restart()
    gpuUsers.restart()
    gpuNodes.restart()
  }
)
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
      <div
        v-else
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
