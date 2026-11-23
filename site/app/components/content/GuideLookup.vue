<script setup lang="ts">
// "Try it" box of the docs (used in Markdown as ::guide-lookup): finds channels by a TV guide ID, an iptv-org or
// Wikidata ID, our ID or a name, with the same index as the search of the website (search.json, loaded on first use).
import type { SearchRow } from '~/composables/useCatalog'

const props = withDefaults(defineProps<{ placeholder?: string, examples?: string[] }>(), {
  placeholder: 'A TV guide ID, an iptv-org ID or a channel name',
  examples: () => ['TF1+1.fr', 'France3.fr@Alsace', 'France3-Alsace.fr', 'Canal+ Sport']
})

const term = ref('')
const { data: index, status, execute } = useApiFile<SearchRow[]>('search.json', { immediate: false })
watch(term, (value) => {
  if (value && status.value === 'idle') execute()
})
const hits = computed(() => searchChannels(index.value, term.value, 8))
const { app } = useRuntimeConfig()
const logo = (id: string) => `${app.baseURL}logos/${id}.png`
const hidden = ref(new Set<string>())

function matched(row: SearchRow): string {
  const t = term.value.trim().toLowerCase()
  if (row[0].toLowerCase().includes(t)) return 'our ID'
  if (fold(row[1]).includes(fold(t))) return 'name'
  return (row[4] ?? '').split(' ').find(x => x.toLowerCase().includes(t)) ?? ''
}
</script>

<template>
  <UCard class="not-prose my-5" variant="subtle">
    <div class="flex flex-col gap-3">
      <UInput
        v-model="term"
        icon="i-lucide-search"
        :placeholder="props.placeholder"
        :loading="status === 'pending'"
        size="lg"
        class="w-full"
      />
      <div class="flex flex-wrap items-center gap-2 text-sm text-muted">
        <span>Try:</span>
        <UButton
          v-for="ex in props.examples"
          :key="ex"
          :label="ex"
          size="xs"
          color="neutral"
          variant="outline"
          @click="term = ex"
        />
      </div>

      <ul v-if="hits.length" class="divide-y divide-default">
        <li v-for="row in hits" :key="row[0]" class="flex items-center gap-3 py-2">
          <div class="flex size-14 shrink-0 items-center justify-center rounded-md bg-elevated p-1.5">
            <img
              v-if="row[3] && !hidden.has(row[0])"
              :src="logo(row[0])"
              :alt="row[1]"
              class="max-h-full max-w-full object-contain"
              loading="lazy"
              @error="hidden.add(row[0])"
            >
            <UIcon v-else name="i-lucide-image-off" class="size-5 text-dimmed" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <ULink :to="channelLink(row[0], row[2])" class="font-medium text-highlighted hover:underline">
                {{ row[1] }}
              </ULink>
              <UBadge :label="row[2].toUpperCase()" color="neutral" variant="subtle" size="sm" />
              <UBadge v-if="!row[3]" label="no logo yet" color="warning" variant="subtle" size="sm" />
            </div>
            <div class="truncate text-xs text-muted">
              <code>{{ row[0] }}</code>
              <span v-if="matched(row)"> · found by <code>{{ matched(row) }}</code></span>
            </div>
          </div>
          <CopyButton :value="row[0]" label="ID" />
        </li>
      </ul>
      <p v-else-if="term.trim().length >= 2 && status === 'success'" class="text-sm text-muted">
        Nothing found. A guide channel is found once it is matched with a score of 0.9 or more; for others, use
        <code>guides.json</code> or ask for an alias.
      </p>
    </div>
  </UCard>
</template>
