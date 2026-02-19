<!--
  Copyright (c) 2023-2024 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { LocationQueryRaw } from 'vue-router'
import ClusterMainLayout from '@/components/ClusterMainLayout.vue'
import { useClusterDataPoller } from '@/composables/DataPoller'
import { jobRequestedGPU, jobAllocatedGPU, useGatewayAPI } from '@/composables/GatewayAPI'
import type { ClusterIndividualJob } from '@/composables/GatewayAPI'
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
const router = useRouter()
const route = useRoute()
const cancelConfirmOpen = ref(false)
const canceling = ref(false)
const cancelError = ref('')
const copying = ref(false)
const copyError = ref('')

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
  }
)

onMounted(() => {
  /* If a job field is in route hash, highlight this field. */
  if (route.hash) {
    const field = route.hash.slice(1) // remove initial hash
    if (isValidJobField(field)) {
      highlightField(field)
    }
  }
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
              class="inline-flex items-center rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-xs hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="copying"
              @click="copyCurrentJob"
            >
              {{ copying ? 'Copying…' : 'Copy' }}
            </button>
            <button
              v-if="canCancel"
              type="button"
              class="inline-flex items-center rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white shadow-xs hover:bg-red-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:cursor-not-allowed disabled:opacity-60"
              @click="cancelConfirmOpen = true"
            >
              Cancel Job
            </button>
          </div>
        </div>
      </div>
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
            class="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white shadow-xs hover:bg-red-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:cursor-not-allowed disabled:opacity-60"
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
