<script setup lang="ts">
import type { ApiLogo } from '~/composables/useCatalog'

// Real logos of the repository, in three rows that scroll slowly (the version made for dark screens).
const { data: logos } = useApiFile<ApiLogo[]>('logos.json')

function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}

const rows = computed(() => {
  const byChannel = new Map<string, ApiLogo>()
  for (const l of logos.value ?? []) {
    if (l.feed) continue
    const seen = byChannel.get(l.channel)
    if (!seen || l.variant === 'white') byChannel.set(l.channel, l)
  }
  // a fixed mix of countries, wide logos only (they read best in a row)
  const list = [...byChannel.values()]
    .filter(l => l.width / l.height >= 1.2)
    .sort((a, b) => hash(a.channel) - hash(b.channel))
    .slice(0, 54)
  return [list.slice(0, 18), list.slice(18, 36), list.slice(36, 54)]
})
</script>

<template>
  <div class="ring-gradient relative overflow-hidden rounded-2xl bg-tile-dark py-6 shadow-2xl shadow-primary/10">
    <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-primary/60 to-transparent" />
    <div
      v-if="logos"
      class="space-y-5"
    >
      <UMarquee
        v-for="(row, i) in rows"
        :key="i"
        :reverse="i % 2 === 1"
        pause-on-hover
        :overlay="false"
        :ui="{ root: '[--duration:60s] [--gap:--spacing(5)]', content: 'items-center' }"
      >
        <NuxtLink
          v-for="l in row"
          :key="l.channel"
          :to="channelLink(l.channel)"
          :aria-label="l.channel"
          class="flex h-16 w-36 shrink-0 items-center justify-center rounded-lg bg-white/[0.07] px-4 ring-1 ring-white/10 transition hover:bg-white/[0.12] hover:ring-primary/50"
        >
          <img
            :src="l.url"
            :alt="`${l.channel} logo`"
            loading="lazy"
            class="max-h-10 max-w-full object-contain"
          >
        </NuxtLink>
      </UMarquee>
    </div>
    <div
      v-else
      class="space-y-5 px-6"
    >
      <USkeleton
        v-for="i in 3"
        :key="i"
        class="h-14 bg-white/5"
      />
    </div>
    <div class="pointer-events-none absolute inset-y-0 left-0 w-16 bg-linear-to-r from-tile-dark to-transparent" />
    <div class="pointer-events-none absolute inset-y-0 right-0 w-16 bg-linear-to-l from-tile-dark to-transparent" />
  </div>
</template>
