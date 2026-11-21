<script setup lang="ts">
import type { ContentNavigationItem } from '@nuxt/content'
import type { NavigationMenuItem } from '@nuxt/ui'

const navigation = inject<Ref<ContentNavigationItem[]>>('navigation')
const docs = computed(() => navigation?.value?.find(i => i.path === '/docs')?.children ?? navigation?.value ?? [])
const route = useRoute()

const items = computed<NavigationMenuItem[]>(() => [
  { label: 'Countries', icon: 'i-lucide-globe', to: '/countries', active: route.path.startsWith('/countries') },
  { label: 'Docs', icon: 'i-lucide-book-open', to: '/docs/getting-started',
    active: route.path.startsWith('/docs') && !route.path.endsWith('/api') },
  { label: 'API', icon: 'i-lucide-braces', to: '/docs/getting-started/api', active: route.path.endsWith('/api') },
  { label: 'Contribute', icon: 'i-lucide-hand-heart', to: '/docs/contribute' }
])
</script>

<template>
  <UHeader to="/">
    <template #title>
      <AppLogo />
    </template>

    <UNavigationMenu
      :items="items"
      variant="link"
    />

    <template #right>
      <UContentSearchButton :collapsed="true" />

      <UColorModeButton />

      <UButton
        icon="i-simple-icons-github"
        to="https://github.com/worldwide-tv-logos/database"
        target="_blank"
        color="neutral"
        variant="ghost"
        aria-label="GitHub"
      />
    </template>

    <template #body>
      <UNavigationMenu
        :items="items"
        orientation="vertical"
        class="-mx-2.5"
      />

      <USeparator class="my-6" />

      <UContentNavigation
        highlight
        :navigation="docs"
      />
    </template>
  </UHeader>
</template>
