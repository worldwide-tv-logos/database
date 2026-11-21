<script setup lang="ts">
import type { Channel } from '~/composables/useCatalog'

const props = defineProps<{ channel: Channel, feed?: string | null }>()
const feed = computed(() => props.feed ?? null)
const main = computed(() => mainLogo(props.channel, feed.value))
const white = computed(() => whiteLogo(props.channel, feed.value))
const id = computed(() => logoId(props.channel.id, feed.value))
</script>

<template>
  <div
    v-if="!main"
    class="rounded-lg border border-dashed border-default p-6 text-center"
  >
    <p class="text-muted">
      No logo for <code class="font-mono text-highlighted">{{ id }}</code> yet.
    </p>
    <div class="mt-4 flex flex-wrap justify-center gap-2">
      <UButton
        :to="forms.add(channel.id, feed)"
        target="_blank"
        icon="i-lucide-image-plus"
        label="Add logo"
      />
      <UButton
        :to="forms.request(channel.id, feed)"
        target="_blank"
        icon="i-lucide-message-square-plus"
        label="Request it"
        color="neutral"
        variant="outline"
      />
    </div>
  </div>

  <div v-else>
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <figure>
        <div class="relative aspect-video rounded-lg bg-tile-dark">
          <img
            :src="(white || main).url"
            :alt="`${id} logo on a dark background`"
            class="absolute inset-0 size-full object-contain p-6"
          >
        </div>
        <figcaption class="mt-1 text-xs text-muted">
          On a dark background{{ white ? ' (white variant)' : '' }}
        </figcaption>
      </figure>
      <figure>
        <div class="relative aspect-video rounded-lg bg-tile-light">
          <img
            :src="main.url"
            :alt="`${id} logo on a light background`"
            class="absolute inset-0 size-full object-contain p-6"
          >
        </div>
        <figcaption class="mt-1 text-xs text-muted">
          On a light background
        </figcaption>
      </figure>
    </div>

    <div class="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
      <span>{{ main.width }} × {{ main.height }} px</span>
      <span>updated {{ main.updated }}</span>
      <span>
        <ULink
          :to="main.url"
          target="_blank"
          class="text-primary"
        >PNG</ULink><template v-if="white">, <ULink
          :to="white.url"
          target="_blank"
          class="text-primary"
        >white PNG</ULink></template>
      </span>
      <CopyButton
        :value="main.url"
        label="Copy URL"
      />
    </div>

    <div class="mt-3 flex flex-wrap gap-2">
      <UButton
        :to="forms.edit(channel.id, feed)"
        target="_blank"
        icon="i-lucide-replace"
        label="Replace logo"
        color="neutral"
        variant="outline"
      />
      <UButton
        :to="forms.remove(channel.id, feed)"
        target="_blank"
        icon="i-lucide-flag"
        label="Report / remove"
        color="error"
        variant="ghost"
      />
    </div>
  </div>
</template>
