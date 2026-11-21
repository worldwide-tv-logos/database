<script setup lang="ts">
import type { Country } from '~/composables/useCatalog'

useSeoMeta({ title: '' })

const { data: countries } = useApiFile<Country[]>('countries.json')

const stats = computed(() => {
  const list = countries.value ?? []
  return [
    { label: 'channels with a logo', value: list.reduce((n, c) => n + c.logos, 0) },
    { label: 'channels listed', value: list.reduce((n, c) => n + c.channels, 0) },
    { label: 'countries with logos', value: list.filter(c => c.logos).length }
  ]
})
const top = computed(() => [...(countries.value ?? [])].filter(c => c.logos).sort((a, b) => b.logos - a.logos).slice(0, 12))

const features = [
  { icon: 'i-lucide-scan', title: 'Transparent and trimmed',
    description: 'Transparent background, trimmed to the drawing, high resolution: SVG originals rendered at 1200 px, longest side 500 to 2000 px, never upscaled.' },
  { icon: 'i-lucide-sun-moon', title: 'Readable everywhere',
    description: 'A white variant for dark logos, so they stay readable on dark screens; a logo made for dark screens gets a dark version for light ones.' },
  { icon: 'i-lucide-link', title: 'One stable address',
    description: 'Every logo is named after its iptv-org channel ID: no guessing, no renaming. A new image keeps the same address.' },
  { icon: 'i-lucide-badge-check', title: 'Current logos only',
    description: 'Old brandings are refused (dated by Wikidata or by the file name), and every logo is checked by eye before it is published.' },
  { icon: 'i-lucide-calendar-clock', title: 'TV guide aliases',
    description: 'The IDs used by TV guides (EPG) that differ from iptv-org are mapped to the right channel and edition.' },
  { icon: 'i-lucide-bot', title: 'Maintained every week',
    description: 'New channels, new brandings and iptv-org changes are followed automatically and reviewed before they are merged.' }
]
</script>

<template>
  <div>
    <UPageHero
      title="TV channel logos from all over the world"
      description="Transparent, trimmed, high resolution. One stable address per logo, named after the iptv-org channel ID. Free JSON API, no key."
      :links="[
        { label: 'Browse countries', to: '/countries', icon: 'i-lucide-globe', size: 'xl' },
        { label: 'API', to: '/docs/getting-started/api', icon: 'i-lucide-braces', size: 'xl', color: 'neutral', variant: 'subtle' }
      ]"
    >
      <div class="mx-auto w-full max-w-2xl">
        <ChannelSearch />
        <div class="mt-8 grid grid-cols-3 gap-4">
          <div
            v-for="s in stats"
            :key="s.label"
            class="text-center"
          >
            <div class="text-2xl font-bold text-highlighted sm:text-3xl">
              <span v-if="countries">{{ s.value.toLocaleString('en') }}</span>
              <USkeleton
                v-else
                class="mx-auto h-8 w-20"
              />
            </div>
            <div class="text-xs text-muted sm:text-sm">
              {{ s.label }}
            </div>
          </div>
        </div>
      </div>
    </UPageHero>

    <UPageSection
      title="Countries with the most logos"
      :links="[{ label: 'All countries', to: '/countries', trailingIcon: 'i-lucide-arrow-right', color: 'neutral', variant: 'outline' }]"
      :ui="{ container: 'py-12 sm:py-16 lg:py-16' }"
    >
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
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
            class="h-16"
          />
        </template>
      </div>
    </UPageSection>

    <UPageSection
      title="Clean logos, ready to use"
      description="Every candidate goes through the same preparation and checks; the best one is kept, then reviewed on contact sheets, each logo on a dark and a light background."
      :features="features"
      :ui="{ container: 'py-12 sm:py-16 lg:py-16' }"
    />

    <UPageSection :ui="{ container: 'py-12 sm:py-16 lg:py-20' }">
      <UPageCTA
        title="A logo is missing?"
        description="Pick a channel, then add its logo with the form, or just ask for it. Requests are checked within a minute and applied the next night."
        variant="subtle"
        :links="[
          { label: 'Contribute', to: '/docs/contribute', icon: 'i-lucide-hand-heart' },
          { label: 'Request a logo', to: 'https://github.com/worldwide-tv-logos/database/issues/new?template=04_logos_request.yml', target: '_blank', color: 'neutral', variant: 'outline' }
        ]"
      />
    </UPageSection>
  </div>
</template>
