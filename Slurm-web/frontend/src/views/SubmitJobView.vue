<!--
  Copyright (c) 2024 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ClusterMainLayout from '@/components/ClusterMainLayout.vue'
import { useGatewayAPI } from '@/composables/GatewayAPI'
import type { SubmitJobRequest } from '@/composables/GatewayAPI'
import { useAuthStore } from '@/stores/auth'
import { useRuntimeStore } from '@/stores/runtime'
import { ChevronLeftIcon } from '@heroicons/vue/20/solid'

const { cluster } = defineProps<{ cluster: string }>()

const router = useRouter()
const gatewayAPI = useGatewayAPI()
const authStore = useAuthStore()
const runtimeStore = useRuntimeStore()
const submitting = ref(false)
const errorMessage = ref('')
const gpuTouched = ref(false)
const jobNameRef = ref<HTMLInputElement | null>(null)
const scriptRef = ref<HTMLTextAreaElement | null>(null)

const usernameForPath = computed(() => authStore.username ?? 'username')

function defaultScript(username: string) {
  return `#!/bin/bash\nsource /home/${username}/anaconda/etc/profile.d/conda.sh`
}

const form = reactive({
  job_name: '',
  qos: 'normal',
  partition: 'debug',
  gpus_per_node: 0,
  cpus_per_task: 4,
  memory_per_node: 16,
  script: '',
  standard_output: '',
  standard_error: ''
})

watch(
  () => form.gpus_per_node,
  (value) => {
    if (!gpuTouched.value) {
      gpuTouched.value = true
      if (value > 0) {
        form.cpus_per_task = value * 10
        form.memory_per_node = value * 100
      }
    }
  }
)

function normalizeScript(script: string): string {
  if (!script.trim()) return ''
  if (script.trimStart().startsWith('#!/bin/bash')) return script
  return `#!/bin/bash\n${script}`
}

async function focusField(target: 'job_name' | 'script') {
  await nextTick()
  const element = target === 'job_name' ? jobNameRef.value : scriptRef.value
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    element.focus()
  }
}

async function validate(): Promise<string> {
  if (!form.job_name.trim()) {
    await focusField('job_name')
    return 'Job name is required.'
  }
  if (!form.qos.trim()) return 'QoS is required.'
  if (!form.partition.trim()) return 'Partition is required.'
  if (form.gpus_per_node < 0 || form.gpus_per_node > 8)
    return 'GPU count must be between 0 and 8.'
  if (form.cpus_per_task < 1 || form.cpus_per_task > 256)
    return 'CPUs per task must be between 1 and 256.'
  if (form.memory_per_node < 1 || form.memory_per_node > 1024)
    return 'Memory per node must be between 1 and 1024.'
  if (!form.script.trim()) {
    await focusField('script')
    return 'Script is required.'
  }
  return ''
}

async function submitJob() {
  errorMessage.value = await validate()
  if (errorMessage.value) return

  const payload: SubmitJobRequest = {
    job_name: form.job_name.trim(),
    qos: form.qos.trim(),
    partition: form.partition.trim(),
    gpus_per_node: form.gpus_per_node,
    cpus_per_task: form.cpus_per_task,
    memory_per_node: form.memory_per_node,
    script: normalizeScript(form.script),
    standard_output: form.standard_output.trim() || '%j.out',
    standard_error: form.standard_error.trim() || '%j.err'
  }

  submitting.value = true
  try {
    await gatewayAPI.submit(cluster, payload)
    router.push({ name: 'jobs', params: { cluster } })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    submitting.value = false
  }
}

function backToJobs() {
  router.push({ name: 'jobs', params: { cluster } })
}
</script>

<template>
  <ClusterMainLayout
    menu-entry="jobs"
    :cluster="cluster"
    :breadcrumb="[{ title: 'Jobs', routeName: 'jobs' }, { title: 'Submit New Job' }]"
  >
    <section class="px-4 py-6 pb-24 sm:px-6 lg:px-8">
      <button
        @click="backToJobs()"
        type="button"
        class="bg-slurmweb dark:bg-slurmweb-verydark hover:bg-slurmweb-dark focus-visible:outline-slurmweb-dark mt-8 mb-8 inline-flex items-center gap-x-2 rounded-md px-3.5 py-2.5 text-sm font-semibold text-white shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2"
      >
        <ChevronLeftIcon class="-ml-0.5 h-5 w-5" aria-hidden="true" />
        Back to jobs
      </button>

      <h1 class="text-2xl font-semibold text-gray-900 dark:text-gray-100">Submit New Job</h1>
      <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
        Fill in all fields to submit a job to the cluster.
      </p>

      <p v-if="errorMessage" class="mt-6 text-sm font-semibold text-red-600">
        {{ errorMessage }}
      </p>

      <div class="mt-6 grid gap-6 max-w-3xl">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">Job name</label>
          <input
            v-model="form.job_name"
            type="text"
            ref="jobNameRef"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
            placeholder="your_job_name"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">QoS</label>
          <input
            v-model="form.qos"
            list="qos-options"
            type="text"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
            placeholder="normal"
          />
          <datalist id="qos-options">
            <option value="normal"></option>
            <option value="high"></option>
          </datalist>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">Partition</label>
          <select
            v-model="form.partition"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
          >
            <option value="debug">debug</option>
            <option value="A100">A100</option>
            <option value="RTX3090">RTX3090</option>
            <option value="RTX4090">RTX4090</option>
            <option value="ADA6000">ADA6000</option>
            <option value="L40S">L40S</option>
            <option value="CPU">cpu</option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            GPU count
          </label>
          <input
            v-model.number="form.gpus_per_node"
            type="number"
            min="0"
            max="8"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            CPUs per task
          </label>
          <input
            v-model.number="form.cpus_per_task"
            type="number"
            min="1"
            max="256"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            Memory per node (GB)
          </label>
          <input
            v-model.number="form.memory_per_node"
            type="number"
            min="1"
            max="1024"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
          />
        </div>

        <div>
          <div class="flex flex-wrap items-center gap-2">
            <label class="text-sm font-medium text-gray-700 dark:text-gray-200">Script</label>
            <span class="text-xs text-gray-500 dark:text-gray-400">
              当前代码执行路径是 /home/{{ usernameForPath }}
            </span>
          </div>
          <textarea
            v-model="form.script"
            rows="6"
            ref="scriptRef"
            class="mt-2 w-full resize-y rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
            :placeholder="defaultScript(usernameForPath)"
          ></textarea>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            Output path
          </label>
          <input
            v-model="form.standard_output"
            type="text"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
            placeholder="%j.out"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">
            Error path
          </label>
          <input
            v-model="form.standard_error"
            type="text"
            class="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-slurmweb focus:ring-slurmweb dark:border-slate-600 dark:bg-slate-900 dark:text-gray-100"
            placeholder="%j.err"
          />
        </div>
      </div>
    </section>

    <button
      v-if="runtimeStore.hasPermission('submit-job')"
      type="button"
      class="fixed bottom-6 right-6 z-50 inline-flex items-center gap-2 rounded-full bg-slurmweb px-6 py-3 text-sm font-semibold text-white shadow-lg transition hover:bg-slurmweb-darker focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slurmweb disabled:cursor-not-allowed disabled:opacity-60"
      :disabled="submitting"
      @click="submitJob"
    >
      <span v-if="submitting">Submitting…</span>
      <span v-else>Submit</span>
    </button>
  </ClusterMainLayout>
</template>
