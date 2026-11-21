<script setup lang="ts">
import type { Country } from '~/composables/useCatalog'

useSeoMeta({ title: '' })

const { open } = useContentSearch()
const { data: countries } = useApiFile<Country[]>('countries.json')
const { data: snippet } = await useAsyncData('home-api', () => queryCollection('home').path('/home/api').first())

const total = computed(() => {
  const list = countries.value ?? []
  return {
    logos: list.reduce((n, c) => n + c.logos, 0),
    channels: list.reduce((n, c) => n + c.channels, 0),
    countries: list.filter(c => c.logos).length
  }
})
const top = computed(() => [...(countries.value ?? [])].filter(c => c.logos).sort((a, b) => b.logos - a.logos).slice(0, 8))
const fmt = (n: number) => n.toLocaleString('en')
</script>

<template>
  <div>
    <!-- 1. hero: the product itself -->
    <div class="relative isolate overflow-hidden border-b border-default">
      <div class="hero-glow -z-10" />
      <div class="hero-grid -z-10" />
      <UPageHero
        orientation="horizontal"
        :ui="{ container: 'py-16 sm:py-24 lg:py-28 gap-12 lg:gap-16', title: 'text-4xl sm:text-6xl tracking-tight', description: 'text-lg text-muted max-w-xl' }"
      >
        <template #headline>
          <UBadge
            variant="subtle"
            color="primary"
            class="rounded-full px-3"
          >
            <span class="size-1.5 rounded-full bg-primary" />
            Open data · updated every night
          </UBadge>
        </template>
        <template #title>
          Every TV channel logo.<br>
          <span class="text-gradient">One clean URL.</span>
        </template>
        <template #description>
          Transparent, trimmed and checked by eye, for {{ countries ? fmt(total.channels) : 'every' }} channels
          from all over the world. Named after the iptv-org channel ID, free to use, no key.
        </template>
        <template #links>
          <div class="flex w-full max-w-xl flex-col gap-3 sm:flex-row">
            <UButton
              icon="i-lucide-search"
              color="neutral"
              variant="outline"
              size="xl"
              class="flex-1 justify-start bg-default/60 text-muted backdrop-blur"
              @click="open = true"
            >
              Search a channel
              <template #trailing>
                <UKbd
                  value="meta"
                  class="ms-auto"
                />
                <UKbd value="K" />
              </template>
            </UButton>
            <UButton
              to="/countries"
              size="xl"
              trailing-icon="i-lucide-arrow-right"
              class="bg-gradient-brand justify-center text-white hover:opacity-90"
            >
              Browse countries
            </UButton>
          </div>
        </template>

        <LogoWall />
      </UPageHero>
    </div>

    <!-- 2. proof strip -->
    <UContainer>
      <dl class="grid grid-cols-2 divide-default border-b border-default py-8 sm:grid-cols-4 sm:divide-x">
        <div
          v-for="s in [
            { label: 'logos published', value: countries ? fmt(total.logos) : null },
            { label: 'channels tracked', value: countries ? fmt(total.channels) : null },
            { label: 'countries covered', value: countries ? String(total.countries) : null },
            { label: 'data refresh', value: 'Nightly' }
          ]"
          :key="s.label"
          class="px-2 py-2 text-center sm:px-6"
        >
          <dt class="text-xs uppercase tracking-wider text-muted">
            {{ s.label }}
          </dt>
          <dd class="mt-1 font-mono text-2xl font-semibold text-highlighted">
            <span v-if="s.value">{{ s.value }}</span>
            <USkeleton
              v-else
              class="mx-auto h-8 w-16"
            />
          </dd>
        </div>
      </dl>
    </UContainer>

    <!-- 3. one URL per logo -->
    <UPageSection
      orientation="horizontal"
      headline="API"
      title="One URL per logo. No key, no sign-up."
      description="Every logo has a stable address derived from its iptv-org channel ID. Use it as is, or read logos.json to know which logos and variants exist."
      :features="[
        { title: 'Drop-in for iptv-org', description: 'logos.json has the same fields as iptv-org\'s, plus country, variant and date.', icon: 'i-lucide-replace' },
        { title: 'Dark-screen ready', description: 'A white version is published for every logo that needs one.', icon: 'i-lucide-moon' },
        { title: 'Editions included', description: 'Regional editions get their own logo, or fall back to their channel.', icon: 'i-lucide-git-branch' }
      ]"
      :links="[{ label: 'API reference', to: '/docs/getting-started/api', trailingIcon: 'i-lucide-arrow-right', color: 'neutral', variant: 'outline' }]"
    >
      <div class="min-w-0 space-y-4">
        <ContentRenderer
          v-if="snippet"
          :value="snippet"
        />
        <div class="grid grid-cols-2 gap-3">
          <div class="flex aspect-[2/1] items-center justify-center rounded-xl bg-tile-light p-5 ring-1 ring-default">
            <img
              :src="`${SITE}logos/fr/France3.fr.png`"
              alt="France 3 logo"
              class="max-h-full max-w-full object-contain"
            >
          </div>
          <div class="flex aspect-[2/1] items-center justify-center rounded-xl bg-tile-dark p-5 ring-1 ring-default">
            <img
              :src="`${SITE}logos/fr/France3.fr.white.png`"
              alt="France 3 white version"
              class="max-h-full max-w-full object-contain"
            >
          </div>
        </div>
      </div>
    </UPageSection>

    <!-- 4. quality, shown on real files -->
    <div class="border-y border-default bg-elevated/30">
      <UPageSection
        orientation="horizontal"
        reverse
        headline="Quality"
        title="Cleaned, checked, ready for any screen."
        description="Logos come from contributors, iptv-org, iptv-epg, Wikidata and the channels' own websites. Each one goes through the same preparation, and old brandings are refused."
        :features="[
          { title: 'Transparent and trimmed', description: 'White frames removed, SVG rendered at 1200 px, never upscaled.', icon: 'i-lucide-scan' },
          { title: 'Current branding only', description: 'Dated with Wikidata and reviewed every week; a doubt is left out.', icon: 'i-lucide-badge-check' },
          { title: 'Readable everywhere', description: 'Dark logos get a white version, white logos a dark one.', icon: 'i-lucide-sun-moon' }
        ]"
      >
        <QualityShowcase />
      </UPageSection>
    </div>

    <!-- 5. coverage -->
    <UPageSection
      headline="Coverage"
      title="Country by country."
      description="Every country listed by iptv-org, with the share of channels on air that already have a logo."
      :links="[{ label: 'All countries', to: '/countries', trailingIcon: 'i-lucide-arrow-right', color: 'neutral', variant: 'outline' }]"
    >
      <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <template v-if="countries">
          <CountryCard
            v-for="c in top"
            :key="c.code"
            :country="c"
          />
        </template>
        <template v-else>
          <USkeleton
            v-for="i in 8"
            :key="i"
            class="h-20"
          />
        </template>
      </div>
    </UPageSection>

    <!-- 6. contribute -->
    <UContainer class="pb-20">
      <div class="ring-gradient relative flex flex-col items-start justify-between gap-6 overflow-hidden rounded-2xl bg-elevated/40 p-8 sm:flex-row sm:items-center">
        <div>
          <p class="text-xl font-semibold text-highlighted">
            A logo is missing or outdated?
          </p>
          <p class="mt-1 text-muted">
            Send it with a form, or just ask for it: requests are checked within a minute and published the next night.
          </p>
        </div>
        <div class="flex shrink-0 gap-2">
          <UButton
            to="/docs/contribute"
            label="Contribute"
            color="neutral"
            variant="solid"
          />
          <UButton
            to="https://github.com/worldwide-tv-logos/database/issues/new?template=04_logos_request.yml"
            target="_blank"
            label="Request a logo"
            color="neutral"
            variant="outline"
          />
        </div>
      </div>
    </UContainer>
  </div>
</template>
