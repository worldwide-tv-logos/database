<script setup lang="ts">
import { onClickOutside } from '@vueuse/core'
import type { SearchRow } from '~/composables/useCatalog'

// Search over every channel (search.json, loaded on first use).
const term = ref('')
const open = ref(false)
const root = useTemplateRef<HTMLElement>('root')
const { data: index, status, execute } = useApiFile<SearchRow[]>('search.json', { immediate: false })

function load() {
  if (!index.value && status.value === 'idle') execute()
}

const hits = computed(() => {
  const t = fold(term.value.trim())
  if (t.length < 2 || !index.value) return []
  const out: SearchRow[] = []
  for (const row of index.value) {
    if (fold(row[1]).includes(t) || row[0].toLowerCase().includes(t)) out.push(row)
    if (out.length >= 40) break
  }
  return out.sort((a, b) => Number(b[3] > 0) - Number(a[3] > 0))
})

watch(term, (t) => {
  load()
  open.value = t.trim().length >= 2
})
onClickOutside(root, () => {
  open.value = false
})
</script>

<template>
  <div
    ref="root"
    class="relative w-full"
  >
    <UInput
      v-model="term"
      icon="i-lucide-search"
      size="xl"
      placeholder="Search a channel by name or ID (e.g. France 3, TF1.fr)"
      aria-label="Search a channel"
      class="w-full"
      :loading="status === 'pending'"
      @focus="load(); open = term.trim().length >= 2"
      @keydown.esc="open = false"
    />
    <div
      v-if="open"
      class="absolute inset-x-0 top-full z-20 mt-2 max-h-96 overflow-y-auto rounded-lg border border-default bg-default text-left shadow-lg"
    >
      <NuxtLink
        v-for="[id, name, cc, n] in hits"
        :key="id"
        :to="channelLink(id)"
        class="flex items-center gap-3 px-4 py-2 hover:bg-elevated"
        @click="open = false"
      >
        <CountryFlag :code="cc" />
        <span class="min-w-0 flex-1 truncate text-highlighted">{{ name }}</span>
        <UBadge
          v-if="n"
          color="success"
          variant="subtle"
          size="sm"
          label="logo"
        />
        <span class="hidden truncate font-mono text-xs text-muted sm:inline">{{ id }}</span>
      </NuxtLink>
      <p
        v-if="index && !hits.length"
        class="px-4 py-3 text-sm text-muted"
      >
        No channel found.
      </p>
    </div>
  </div>
</template>
