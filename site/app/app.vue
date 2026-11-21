<script setup lang="ts">
import type { SearchRow } from '~/composables/useCatalog'

const { seo } = useAppConfig()

const { data: navigation } = await useAsyncData('navigation', () => queryCollectionNavigation('docs'))
const { data: files } = useLazyAsyncData('search', () => queryCollectionSearchSections('docs'), {
  server: false
})

useSeoMeta({
  titleTemplate: (t?: string) => t ? `${t} | ${seo?.siteName}` : seo?.siteName,
  description: 'Clean TV channel logos from all over the world, keyed by iptv-org channel ID: transparent, trimmed, high resolution.',
  ogSiteName: seo?.siteName
})

provide('navigation', navigation)

// one search (⌘K) for the channels and the documentation; the channel index is loaded when the search opens
const searchTerm = ref('')
const { open } = useContentSearch()
const { data: index, status, execute } = useApiFile<SearchRow[]>('search.json', { immediate: false })
watch(open, (value) => {
  if (value && status.value === 'idle') execute()
})
const groups = computed(() => {
  const hits = searchChannels(index.value, searchTerm.value)
  return hits.length
    ? [{
        id: 'channels',
        label: 'Channels',
        ignoreFilter: true,
        items: hits.map(([id, name, cc, n]) => ({
          label: name,
          suffix: id,
          to: channelLink(id),
          avatar: { src: flagUrl(cc), alt: cc.toUpperCase(), size: 'xs' as const },
          chip: n ? { color: 'success' as const, size: 'sm' as const } : undefined
        }))
      }]
    : []
})

const searchLinks = [
  { label: 'Countries', icon: 'i-lucide-globe', to: '/countries' },
  { label: 'API', icon: 'i-lucide-braces', to: '/docs/getting-started/api' },
  { label: 'Contribute', icon: 'i-lucide-hand-heart', to: '/docs/contribute' }
]
</script>

<template>
  <UApp>
    <NuxtLoadingIndicator color="var(--ui-primary)" />

    <AppHeader />

    <UMain>
      <NuxtLayout>
        <NuxtPage />
      </NuxtLayout>
    </UMain>

    <AppFooter />

    <ClientOnly>
      <LazyUContentSearch
        v-model:search-term="searchTerm"
        :files="files"
        :navigation="navigation"
        :links="searchLinks"
        :groups="groups"
        :loading="status === 'pending'"
        :fuse="{ resultLimit: 40 }"
        placeholder="Search a channel (name or ID) or the docs"
      />
    </ClientOnly>
  </UApp>
</template>
