<script setup lang="ts">
import type { Country, CountryData } from '~/composables/useCatalog'

const PAGE = 120 // channels shown at once

const route = useRoute()
const router = useRouter()
const cc = computed(() => String(route.params.cc).toLowerCase())

// name of the country in the static page (from the list), then its channels in the browser
const { data: countries } = useApiFile<Country[]>('countries.json')
const { data, status, error } = useApiFile<CountryData>(() => `countries/${cc.value}.json`)
const name = computed(() => data.value?.name || countries.value?.find(c => c.code === cc.value)?.name || cc.value.toUpperCase())

useSeoMeta({
  title: () => name.value,
  description: () => `TV channel logos of ${name.value}.`
})

const filter = ref('')
const mode = ref<'all' | 'logo' | 'missing'>('all')
const closed = ref(false)
const shown = ref(PAGE)
watch([filter, mode, closed], () => {
  shown.value = PAGE
})

const onAir = computed(() => (data.value?.channels ?? []).filter(c => !c.closed))
const withLogo = computed(() => onAir.value.filter(c => c.logos.length).length)

const list = computed(() => {
  const f = fold(filter.value)
  return (data.value?.channels ?? []).filter(c => (closed.value || !c.closed || c.logos.length)
    && (mode.value === 'all' || (mode.value === 'logo' ? c.logos.length : !c.logos.length))
    && (!f || fold(c.name).includes(f) || c.id.toLowerCase().includes(f) || (c.alt_names || []).some(a => fold(a).includes(f))))
    .sort((a, b) => Number(b.logos.length > 0) - Number(a.logos.length > 0)) // stable: by name within each group
})

// channel opened in the side panel: ?channel=<id>
const selectedId = computed(() => typeof route.query.channel === 'string' ? route.query.channel : null)
const selected = computed(() => selectedId.value ? data.value?.channels.find(c => c.id === selectedId.value) : undefined)
const panelOpen = computed({
  get: () => !!selectedId.value,
  set: (v: boolean) => {
    if (!v) router.replace({ query: {} })
  }
})
</script>

<template>
  <UContainer>
    <UPageHeader :description="data ? `${withLogo} of ${onAir.length} channels on air have a logo. Missing one? Open a channel and use Add logo.` : undefined">
      <template #headline>
        <UBreadcrumb :items="[{ label: 'Countries', to: '/countries' }, { label: name }]" />
      </template>
      <template #title>
        <span class="inline-flex items-center gap-3">
          <CountryFlag
            :code="cc"
            :name="name"
          />
          {{ name }}
        </span>
      </template>
    </UPageHeader>

    <UPageBody>
      <div class="flex flex-wrap items-center gap-3">
        <UInput
          v-model="filter"
          icon="i-lucide-filter"
          placeholder="Filter channels by name or ID"
          aria-label="Filter channels"
          class="w-full sm:w-80"
        />
        <UTabs
          v-model="mode"
          :items="[{ label: 'All', value: 'all' }, { label: 'With logo', value: 'logo' }, { label: 'Missing', value: 'missing' }]"
          :content="false"
          size="sm"
        />
        <USwitch
          v-model="closed"
          label="Show closed channels"
        />
      </div>

      <UAlert
        v-if="error"
        color="error"
        variant="subtle"
        title="This country could not be loaded."
        :actions="[{ label: 'All countries', to: '/countries', color: 'neutral', variant: 'outline' }]"
      />
      <template v-else-if="status === 'success' && data">
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          <ChannelCard
            v-for="c in list.slice(0, shown)"
            :key="c.id"
            :channel="c"
          />
        </div>
        <p
          v-if="!list.length"
          class="text-muted"
        >
          No channel found.
        </p>
        <div
          v-if="list.length > shown"
          class="flex justify-center"
        >
          <UButton
            :label="`Show more (${list.length - shown} left)`"
            color="neutral"
            variant="outline"
            @click="shown += PAGE"
          />
        </div>
      </template>
      <div
        v-else
        class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6"
      >
        <USkeleton
          v-for="i in 18"
          :key="i"
          class="aspect-[4/3]"
        />
      </div>
    </UPageBody>

    <USlideover
      v-model:open="panelOpen"
      :title="selected?.name || selectedId || ''"
      :description="selected ? `${name} · ${selected.feeds.length} edition${selected.feeds.length === 1 ? '' : 's'}` : undefined"
      :ui="{ content: 'max-w-2xl' }"
    >
      <template #body>
        <ChannelPanel
          v-if="selected"
          :channel="selected"
        />
        <p
          v-else-if="data"
          class="text-muted"
        >
          Channel <code class="font-mono">{{ selectedId }}</code> not found in {{ name }}.
        </p>
        <USkeleton
          v-else
          class="h-64"
        />
      </template>
    </USlideover>
  </UContainer>
</template>
