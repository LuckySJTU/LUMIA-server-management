/*
 * Copyright (c) 2024 Rackslab
 *
 * This file is part of Slurm-web.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

import type { ClusterIndividualJob, SubmitJobRequest } from '@/composables/GatewayAPI'
import { jobRequestedGPU } from '@/composables/GatewayAPI'

function normalizeText(value: string | undefined): string {
  if (!value || value === 'NONE') return ''
  return value
}

function requestedTRESCount(job: ClusterIndividualJob, type: string): number | undefined {
  const item = job.tres.requested.find((value) => value.type === type)
  if (!item || item.count < 0) return undefined
  return item.count
}

function requestedNodeCount(job: ClusterIndividualJob): number {
  const nodeFromTRES = requestedTRESCount(job, 'node')
  if (nodeFromTRES && nodeFromTRES > 0) return nodeFromTRES
  if (job.node_count && job.node_count.set && job.node_count.number > 0) {
    return job.node_count.number
  }
  return 1
}

export function buildSubmitPayloadFromJob(job: ClusterIndividualJob): SubmitJobRequest {
  const nodeCount = requestedNodeCount(job)
  if (nodeCount > 1) {
    throw new Error('Copy is only supported for single-node jobs.')
  }

  const cpuRequested = requestedTRESCount(job, 'cpu')
  const memRequestedMb = requestedTRESCount(job, 'mem')
  const gpuRequested = jobRequestedGPU(job).count

  const cpusPerTask = Math.max(cpuRequested ?? job.cpus?.number ?? 4, 1)
  const memoryPerNodeGb = Math.max(Math.ceil((memRequestedMb ?? 16 * 1024) / 1024), 1)
  const gpusPerNode = Math.max(gpuRequested ?? 0, 0)

  // Copy flow explicitly prefers script, then falls back to command.
  const script = normalizeText(job.script) || normalizeText(job.command)

  return {
    job_name: `${job.name || 'your_job_name'}_copy`,
    qos: job.qos || 'normal',
    partition: job.partition || 'debug',
    gpus_per_node: gpusPerNode,
    cpus_per_task: cpusPerTask,
    memory_per_node: memoryPerNodeGb,
    script,
    standard_output: normalizeText(job.standard_output),
    standard_error: normalizeText(job.standard_error)
  }
}
