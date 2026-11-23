<script setup lang="ts">
import type { Channel } from '~/composables/useCatalog'

const props = defineProps<{ channel: Channel }>()
const logo = computed(() => cardLogo(props.channel))
const editions = computed(() => props.channel.feeds.length)
</script>

<template>
  <UPageCard
    :to="channelLink(channel.id, channel.country)"
    variant="outline"
    spotlight
    :ui="{ container: 'p-2 sm:p-2 gap-y-0', header: 'mb-3 w-full', wrapper: 'px-1 pb-1 min-w-0 w-full', title: 'truncate w-full text-sm', description: 'truncate w-full font-mono text-xs' }"
    :title="channel.name"
    :description="channel.id"
  >
    <template #header>
      <span class="relative block aspect-video overflow-hidden rounded-md bg-tile-dark">
        <img
          v-if="logo"
          :src="logo.url"
          :alt="`${channel.name} logo`"
          loading="lazy"
          class="absolute inset-0 size-full object-contain p-4"
        >
        <span
          v-else
          class="absolute inset-0 flex flex-col items-center justify-center gap-1 text-xs text-neutral-500"
        >
          <UIcon
            name="i-lucide-image-off"
            class="size-5"
          />
          No logo yet
        </span>
      </span>
    </template>
    <template
      v-if="channel.closed || editions > 1"
      #footer
    >
      <span class="flex flex-wrap gap-1">
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
    </template>
  </UPageCard>
</template>
