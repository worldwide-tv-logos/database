<script setup lang="ts">
import type { Channel, Feed } from '~/composables/useCatalog'

const props = defineProps<{ channel: Channel, feed: Feed }>()
const own = computed(() => mainLogo(props.channel, props.feed.id))
const shown = computed(() => own.value ? darkLogo(props.channel, props.feed.id) : darkLogo(props.channel))
</script>

<template>
  <div class="flex items-center gap-3 rounded-lg border border-default p-2">
    <div class="relative flex h-14 w-24 shrink-0 items-center justify-center rounded-md bg-tile-dark p-2">
      <img
        v-if="shown"
        :src="shown.url"
        alt=""
        loading="lazy"
        class="size-full object-contain"
        :class="{ 'opacity-40': !own }"
      >
      <span
        v-else
        class="text-xs text-neutral-400"
      >No logo</span>
    </div>
    <div class="min-w-0 flex-1">
      <div class="truncate font-medium text-highlighted">
        {{ feed.name }}
        <UBadge
          v-if="!own && shown"
          color="neutral"
          variant="subtle"
          size="sm"
          label="channel logo"
          class="ms-1"
        />
      </div>
      <div class="truncate font-mono text-xs text-muted">
        {{ logoId(channel.id, feed.id) }}
      </div>
      <div class="mt-1 flex flex-wrap gap-x-3 text-sm">
        <template v-if="own">
          <ULink
            :to="own.url"
            target="_blank"
            class="text-primary"
          >PNG</ULink>
          <ULink
            :to="forms.edit(channel.id, feed.id)"
            target="_blank"
            class="text-primary"
          >Replace</ULink>
          <ULink
            :to="forms.remove(channel.id, feed.id)"
            target="_blank"
            class="text-error"
          >Remove</ULink>
        </template>
        <span
          v-else-if="QUALITY_FEED.test(feed.id)"
          class="text-muted"
        >Same programmes (quality or +1 version): uses the channel logo</span>
        <template v-else>
          <ULink
            :to="forms.add(channel.id, feed.id)"
            target="_blank"
            class="text-primary"
          >Add its logo</ULink>
          <ULink
            :to="forms.request(channel.id, feed.id)"
            target="_blank"
            class="text-primary"
          >Request</ULink>
        </template>
      </div>
    </div>
  </div>
</template>
