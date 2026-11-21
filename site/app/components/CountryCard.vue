<script setup lang="ts">
import type { Country } from '~/composables/useCatalog'

const props = defineProps<{ country: Country }>()
const share = computed(() => props.country.channels ? Math.round(100 * props.country.logos / props.country.channels) : 0)
</script>

<template>
  <NuxtLink
    :to="`/countries/${country.code}`"
    class="group flex items-center gap-3 rounded-lg border border-default bg-default p-3 transition hover:border-primary/60 hover:bg-elevated/50 focus-visible:outline-2 focus-visible:outline-primary"
  >
    <CountryFlag
      :code="country.code"
      :name="country.name"
      class="text-2xl"
    />
    <span class="min-w-0 flex-1">
      <span class="block truncate font-medium text-highlighted">{{ country.name }}</span>
      <span class="block text-xs text-muted">{{ country.logos.toLocaleString('en') }} / {{ country.channels.toLocaleString('en') }} channels</span>
      <UProgress
        :model-value="share"
        size="xs"
        class="mt-1.5"
      />
    </span>
  </NuxtLink>
</template>
