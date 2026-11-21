<script setup lang="ts">
import type { Country } from '~/composables/useCatalog'

const props = defineProps<{ country: Country }>()
const share = computed(() => props.country.channels ? Math.round(100 * props.country.logos / props.country.channels) : 0)
</script>

<template>
  <UPageCard
    :to="`/countries/${country.code}`"
    variant="outline"
    spotlight
    :ui="{ container: 'p-4 sm:p-4 gap-y-0', wrapper: 'w-full', title: 'w-full', description: 'w-full' }"
  >
    <template #title>
      <span class="flex w-full items-center gap-3">
        <CountryFlag
          :code="country.code"
          :name="country.name"
          size="md"
        />
        <span class="min-w-0 flex-1 truncate">{{ country.name }}</span>
        <span class="font-mono text-xs font-normal text-muted">{{ share }}%</span>
      </span>
    </template>
    <template #description>
      <span class="mt-3 block">
        <UProgress
          :model-value="share"
          size="xs"
          :ui="{ indicator: 'bg-gradient-brand' }"
        />
        <span class="mt-2 block text-xs text-muted">{{ country.logos.toLocaleString('en') }} of {{ country.channels.toLocaleString('en') }} channels</span>
      </span>
    </template>
  </UPageCard>
</template>
