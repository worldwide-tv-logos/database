<script setup lang="ts">
import type { Country } from '~/composables/useCatalog'

useSeoMeta({ title: 'Countries', description: 'TV channel logos by country.' })

const { data: countries, status, error } = useApiFile<Country[]>('countries.json')
const filter = ref('')
const mode = ref<'logos' | 'all'>('logos')

const list = computed(() => {
  const f = fold(filter.value)
  return (countries.value ?? [])
    .filter(c => (mode.value === 'all' || c.logos) && (!f || fold(c.name).includes(f) || c.code.includes(f)))
    .sort((a, b) => (mode.value === 'logos' ? b.logos - a.logos : 0) || a.name.localeCompare(b.name))
})
</script>

<template>
  <UContainer>
    <UPageHeader
      title="Countries"
      description="Channels of every country listed by iptv-org, with the logos of this repository."
    />

    <UPageBody>
      <div class="flex flex-wrap items-center gap-3">
        <UInput
          v-model="filter"
          icon="i-lucide-filter"
          placeholder="Filter countries"
          aria-label="Filter countries"
          class="w-full sm:w-72"
        />
        <UTabs
          v-model="mode"
          :items="[{ label: 'With logos', value: 'logos' }, { label: 'All', value: 'all' }]"
          :content="false"
          size="sm"
        />
      </div>

      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="The list of countries could not be loaded."
      />
      <div
        v-else
        class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      >
        <template v-if="status === 'success'">
          <CountryCard
            v-for="c in list"
            :key="c.code"
            :country="c"
          />
          <p
            v-if="!list.length"
            class="text-muted"
          >
            No country found.
          </p>
        </template>
        <template v-else>
          <USkeleton
            v-for="i in 12"
            :key="i"
            class="h-16"
          />
        </template>
      </div>
    </UPageBody>
  </UContainer>
</template>
