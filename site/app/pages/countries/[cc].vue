<script setup lang="ts">
import type { Country, CountryData } from '~/composables/useCatalog'

const PER_PAGE = 48

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
const categories = ref<string[]>([])
const closed = ref(false)
const page = ref(1)
watch([filter, mode, categories, closed], () => {
  page.value = 1
})

const onAir = computed(() => (data.value?.channels ?? []).filter(c => !c.closed))
const withLogo = computed(() => onAir.value.filter(c => c.logos.length).length)
const share = computed(() => onAir.value.length ? Math.round(100 * withLogo.value / onAir.value.length) : 0)
const allCategories = computed(() => [...new Set((data.value?.channels ?? []).flatMap(c => c.categories ?? []))].sort())

const list = computed(() => {
  const f = fold(filter.value)
  return (data.value?.channels ?? []).filter(c => (closed.value || !c.closed || c.logos.length)
    && (mode.value === 'all' || (mode.value === 'logo' ? c.logos.length : !c.logos.length))
    && (!categories.value.length || (c.categories ?? []).some(x => categories.value.includes(x)))
    && (!f || fold(c.name).includes(f) || c.id.toLowerCase().includes(f) || (c.alt_names || []).some(a => fold(a).includes(f))))
    .sort((a, b) => Number(b.logos.length > 0) - Number(a.logos.length > 0)) // stable: by name within each group
})
const pageItems = computed(() => list.value.slice((page.value - 1) * PER_PAGE, page.value * PER_PAGE))

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
  <div class="relative isolate">
    <div class="hero-glow -z-10 h-72 opacity-60" />
    <UContainer>
      <UPageHeader :ui="{ root: 'border-none pb-4' }">
        <template #headline>
          <UBreadcrumb :items="[{ label: 'Countries', to: '/countries' }, { label: name }]" />
        </template>
        <template #title>
          <span class="inline-flex items-center gap-3">
            <CountryFlag
              :code="cc"
              :name="name"
              size="lg"
            />
            {{ name }}
          </span>
        </template>
        <template #description>
          <span
            v-if="data"
            class="flex max-w-md flex-col gap-2"
          >
            <span>{{ withLogo }} of {{ onAir.length }} channels on air have a logo. Missing one? Open a channel and use
              Add logo. A channel not listed? <ULink
                :to="forms.channelAdd(cc)"
                target="_blank"
                class="text-primary"
              >Add it</ULink>.</span>
            <UProgress
              :model-value="share"
              size="sm"
              :ui="{ indicator: 'bg-gradient-brand' }"
            />
          </span>
        </template>
      </UPageHeader>

      <UPageBody>
        <div class="flex flex-wrap items-center gap-3 rounded-xl border border-default bg-elevated/40 p-3 backdrop-blur">
          <UInput
            v-model="filter"
            icon="i-lucide-search"
            placeholder="Filter by name or ID"
            aria-label="Filter channels"
            class="w-full sm:w-72"
          >
            <template
              v-if="filter"
              #trailing
            >
              <UButton
                icon="i-lucide-x"
                color="neutral"
                variant="link"
                size="xs"
                aria-label="Clear"
                @click="filter = ''"
              />
            </template>
          </UInput>
          <UTabs
            v-model="mode"
            :items="[{ label: 'All', value: 'all' }, { label: 'With logo', value: 'logo' }, { label: 'Missing', value: 'missing' }]"
            :content="false"
            size="sm"
          />
          <USelectMenu
            v-model="categories"
            :items="allCategories"
            multiple
            placeholder="Categories"
            icon="i-lucide-tags"
            class="w-full sm:w-52"
          />
          <USwitch
            v-model="closed"
            label="Closed channels"
            class="sm:ms-auto"
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
          <p class="text-sm text-muted">
            {{ list.length }} channel{{ list.length === 1 ? '' : 's' }}
          </p>
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            <ChannelCard
              v-for="c in pageItems"
              :key="c.id"
              :channel="c"
            />
          </div>
          <UEmpty
            v-if="!list.length"
            icon="i-lucide-search-x"
            title="No channel found"
            description="Try another name, or clear the filters."
          />
          <div
            v-if="list.length > PER_PAGE"
            class="flex justify-center"
          >
            <UPagination
              v-model:page="page"
              :total="list.length"
              :items-per-page="PER_PAGE"
              show-edges
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
    </UContainer>

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
        <UEmpty
          v-else-if="data"
          icon="i-lucide-tv"
          :title="`Channel ${selectedId} not found in ${name}`"
        />
        <USkeleton
          v-else
          class="h-64"
        />
      </template>
    </USlideover>
  </div>
</template>
