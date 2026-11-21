<script setup lang="ts">
import { useClipboard } from '@vueuse/core'

defineProps<{ value: string, label?: string }>()
const { copy, copied } = useClipboard({ copiedDuring: 1500 })
</script>

<template>
  <UButton
    :icon="copied ? 'i-lucide-copy-check' : 'i-lucide-copy'"
    :label="label"
    :aria-label="label || 'Copy'"
    color="neutral"
    variant="ghost"
    size="xs"
    @click="copy(value)"
  />
</template>
