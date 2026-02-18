<!--
  Copyright (c) 2024 Rackslab

  This file is part of Slurm-web.

  SPDX-License-Identifier: GPL-3.0-or-later
-->

<script setup lang="ts">
const {
  field,
  monospace = false,
  preserveLines = false,
  scrollable = false
} = defineProps<{
  field: string | number | null | undefined
  monospace?: boolean
  preserveLines?: boolean
  scrollable?: boolean
}>()
</script>

<template>
  <dd
    :class="[
      monospace ? 'font-mono' : '',
      preserveLines ? 'whitespace-pre-wrap break-words' : '',
      scrollable ? 'max-h-72 overflow-auto rounded-md border border-gray-200 p-2 dark:border-gray-700' : '',
      'mt-1 text-sm leading-6 text-gray-700 sm:col-span-2 sm:mt-0 dark:text-gray-300'
    ]"
  >
    {{ field ?? '' }}
  </dd>
</template>
