<script setup lang="ts">
import type { NuxtError } from '#app'

defineProps<{
  error: NuxtError
}>()

useSeoMeta({
  title: 'Page not found',
  description: 'This page could not be found.'
})

const { data: navigation } = await useAsyncData('navigation', () => queryCollectionNavigation('docs'))

provide('navigation', navigation)
</script>

<template>
  <UApp>
    <AppHeader />

    <UError :error="error" />

    <AppFooter />
  </UApp>
</template>
