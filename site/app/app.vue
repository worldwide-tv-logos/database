<script setup lang="ts">
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
</script>

<template>
  <UApp>
    <NuxtLoadingIndicator />

    <AppHeader />

    <UMain>
      <NuxtLayout>
        <NuxtPage />
      </NuxtLayout>
    </UMain>

    <AppFooter />

    <ClientOnly>
      <LazyUContentSearch
        :files="files"
        :navigation="navigation"
        :links="searchLinks"
      />
    </ClientOnly>
  </UApp>
</template>

<script lang="ts">
const searchLinks = [
  { label: 'Countries', icon: 'i-lucide-globe', to: '/countries' },
  { label: 'API', icon: 'i-lucide-braces', to: '/docs/getting-started/api' },
  { label: 'Contribute', icon: 'i-lucide-hand-heart', to: '/docs/contribute' }
]
</script>
