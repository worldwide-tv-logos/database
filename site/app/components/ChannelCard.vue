<script setup lang="ts">
import type { Channel } from '~/composables/useCatalog'

const props = defineProps<{ channel: Channel }>()
const logo = computed(() => cardLogo(props.channel))
const editions = computed(() => props.channel.feeds.length)
</script>

<template>
  <NuxtLink
    :to="channelLink(channel.id)"
    class="group flex flex-col overflow-hidden rounded-lg border border-default bg-default transition hover:border-primary/60 focus-visible:outline-2 focus-visible:outline-primary"
  >
    <span class="relative block aspect-video bg-tile-dark">
      <img
        v-if="logo"
        :src="logo.url"
        :alt="`${channel.name} logo`"
        loading="lazy"
        class="absolute inset-0 size-full object-contain p-4 transition group-hover:scale-105"
      >
      <span
        v-else
        class="absolute inset-0 flex items-center justify-center text-sm text-neutral-400"
      >No logo yet</span>
    </span>
    <span class="flex flex-col gap-1 p-3">
      <span class="truncate font-medium text-highlighted">{{ channel.name }}</span>
      <span class="truncate font-mono text-xs text-muted">{{ channel.id }}</span>
      <span
        v-if="channel.closed || editions > 1"
        class="flex flex-wrap gap-1"
      >
        <UBadge
          v-if="channel.closed"
          color="error"
          variant="subtle"
          size="sm"
          label="closed"
        />
        <UBadge
          v-if="editions > 1"
          color="neutral"
          variant="subtle"
          size="sm"
          :label="`${editions} editions`"
        />
      </span>
    </span>
  </NuxtLink>
</template>
