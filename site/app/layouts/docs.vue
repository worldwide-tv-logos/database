<script setup lang="ts">
import type { ContentNavigationItem } from '@nuxt/content'

const navigation = inject<Ref<ContentNavigationItem[]>>('navigation')
const docs = computed(() => navigation?.value?.find(i => i.path === '/docs')?.children ?? navigation?.value ?? [])
</script>

<template>
  <UContainer>
    <UPage>
      <template #left>
        <UPageAside>
          <UContentNavigation
            highlight
            :navigation="docs"
          />
        </UPageAside>
      </template>

      <slot />
    </UPage>
  </UContainer>
</template>
