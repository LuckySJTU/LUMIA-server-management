<!--
  Copyright (c) 2025 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
import { jobResourcesGPU } from '@/composables/GatewayAPI'
import type { ClusterJob } from '@/composables/GatewayAPI'
import {
  ServerIcon,
  CpuChipIcon,
  TableCellsIcon,
  Square3Stack3DIcon
} from '@heroicons/vue/24/outline'

const { job } = defineProps<{ job: ClusterJob }>()
const gpu = jobResourcesGPU(job)

function parseTRESMap(tresString: string): Record<string, number> {
  const result: Record<string, number> = {}
  for (const raw of tresString.split(',')) {
    const part = raw.trim()
    if (!part) continue
    const [key, value] = part.split('=')
    if (!key || value === undefined) continue
    const num = Number.parseFloat(value)
    if (Number.isNaN(num)) continue
    result[key] = num
  }
  return result
}

function parseMemoryValueToMB(value: string): number {
  const match = value.trim().match(/^(\d+(?:\.\d+)?)([KMGTP]?)$/i)
  if (!match) return 0
  const amount = Number.parseFloat(match[1])
  const unit = (match[2] || 'M').toUpperCase()
  if (unit === 'K') return amount / 1024
  if (unit === 'M') return amount
  if (unit === 'G') return amount * 1024
  if (unit === 'T') return amount * 1024 * 1024
  if (unit === 'P') return amount * 1024 * 1024 * 1024
  return amount
}

function parseMemoryMBFromTRESRequest(tresRequest: string): number {
  let memoryMB = 0
  for (const raw of tresRequest.split(',')) {
    const tres = raw.split('(')[0].replace('=', ':')
    const items = tres.split(':')
    if (items[0] !== 'mem' || items.length < 2) continue
    memoryMB += parseMemoryValueToMB(items[1])
  }
  return memoryMB
}

function parseMemoryMBFromTRESReqString(tresReq: string): number {
  const parts = tresReq.split(',')
  for (const part of parts) {
    const trimmed = part.trim()
    if (!trimmed.startsWith('mem=')) continue
    const value = trimmed.slice('mem='.length).trim()
    return parseMemoryValueToMB(value)
  }
  return 0
}

function allocatedNodeCount(job: ClusterJob): number | null {
  if (!job.tres_alloc_str) return null
  const tres = parseTRESMap(job.tres_alloc_str)
  if (typeof tres.node === 'number' && tres.node > 0) return Math.ceil(tres.node)
  return null
}

function allocatedCPUCount(job: ClusterJob): number | null {
  if (!job.tres_alloc_str) return null
  const tres = parseTRESMap(job.tres_alloc_str)
  if (typeof tres.cpu === 'number' && tres.cpu > 0) return Math.ceil(tres.cpu)
  return null
}

function allocatedMemoryGB(job: ClusterJob): number | null {
  if (!job.tres_alloc_str) return null
  const parts = job.tres_alloc_str.split(',')
  for (const raw of parts) {
    const part = raw.trim()
    if (!part.startsWith('mem=')) continue
    const memValue = part.slice('mem='.length)
    const memMB = parseMemoryValueToMB(memValue)
    if (memMB <= 0) return null
    return Math.ceil(memMB / 1024)
  }
  return null
}

function requestedMemoryGB(job: ClusterJob): number | null {
  const mbToGBOrNull = (mb: number): number | null => {
    if (mb <= 0) return null
    return Math.ceil(mb / 1024)
  }

  if (job.tres_req_str && job.tres_req_str.length) {
    const gb = mbToGBOrNull(parseMemoryMBFromTRESReqString(job.tres_req_str))
    if (gb !== null) return gb
  }

  if (job.tres_per_job && job.tres_per_job.length) {
    return mbToGBOrNull(parseMemoryMBFromTRESRequest(job.tres_per_job))
  }
  if (job.tres_per_node && job.tres_per_node.length && job.node_count.set) {
    const mb = parseMemoryMBFromTRESRequest(job.tres_per_node) * job.node_count.number
    return mbToGBOrNull(mb)
  }
  if (
    job.tres_per_socket &&
    job.tres_per_socket.length &&
    job.node_count.set &&
    job.sockets_per_node.set
  ) {
    const mb =
      parseMemoryMBFromTRESRequest(job.tres_per_socket) *
      job.node_count.number *
      job.sockets_per_node.number
    return mbToGBOrNull(mb)
  }
  if (job.tres_per_task && job.tres_per_task.length && job.tasks.set) {
    const mb = parseMemoryMBFromTRESRequest(job.tres_per_task) * job.tasks.number
    return mbToGBOrNull(mb)
  }
  return null
}

const nodes = allocatedNodeCount(job) ?? job.node_count.number
const cpus = allocatedCPUCount(job) ?? job.cpus.number
const memoryGB = allocatedMemoryGB(job) ?? requestedMemoryGB(job)
</script>
<template>
  <span class="mr-2 inline-flex">
    <ServerIcon class="mr-0.5 h-5 w-5" aria-hidden="true" />
    {{ nodes }}
  </span>
  <span class="mr-2 inline-flex">
    <CpuChipIcon class="mr-0.5 h-5 w-5" aria-hidden="true" />
    {{ cpus }}
  </span>
  <span class="mr-2 inline-flex">
    <TableCellsIcon class="mr-0.5 h-5 w-5" aria-hidden="true" />
    {{ memoryGB !== null ? memoryGB : '-' }}
  </span>
  <span v-if="gpu.count" class="inline-flex">
    <Square3Stack3DIcon class="mr-0.5 h-5 w-5" aria-hidden="true" />
    {{ gpu.count }}
    <span v-if="!gpu.reliable" class="text-gray-400">~</span>
  </span>
</template>
