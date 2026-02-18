<!--
  Copyright (c) 2026 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
interface JobHistoryEntry {
  timestamp: number
  label: string
}

const { entries } = defineProps<{
  entries: JobHistoryEntry[]
}>()

function pad2(n: number): string {
  return n.toString().padStart(2, '0')
}

function formatTimestamp(timestamp: number): string {
  const d = new Date(timestamp * 1000)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(
    d.getHours()
  )}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}
</script>

<template>
  <dd class="mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300">
    <ul v-if="entries.length" class="space-y-1">
      <li v-for="(entry, idx) in entries" :key="`${entry.timestamp}-${entry.label}-${idx}`">
        <span class="font-mono">{{ formatTimestamp(entry.timestamp) }}</span>
        <span class="ml-2">{{ entry.label }}</span>
      </li>
    </ul>
    <span v-else>-</span>
  </dd>
</template>
