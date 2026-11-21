<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { Alias, Channel } from '~/composables/useCatalog'

const props = defineProps<{ channel: Channel }>()
const ch = computed(() => props.channel)
// the main edition uses the channel logo: listed only when it has a logo of its own
const aliasColumns: TableColumn<Alias>[] = [
  { accessorKey: 'epg_id', header: 'Guide ID' },
  { accessorKey: 'source', header: 'Guide' },
  { accessorKey: 'feed', header: 'Edition' },
  { id: 'actions', header: '' }
]
const editions = computed(() => ch.value.feeds.filter(f => !(f.is_main && !mainLogo(ch.value, f.id))))
</script>

<template>
  <div class="space-y-8">
    <div class="space-y-2">
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <span class="text-muted">ID</span>
        <code class="font-mono text-highlighted">{{ ch.id }}</code>
        <CopyButton :value="ch.id" />
      </div>
      <div class="flex flex-wrap gap-2">
        <UBadge
          v-if="ch.network"
          color="neutral"
          variant="outline"
          :label="`Network: ${ch.network}`"
        />
        <UBadge
          v-for="cat in ch.categories || []"
          :key="cat"
          color="neutral"
          variant="subtle"
          :label="cat"
        />
        <UBadge
          v-if="ch.launched"
          color="neutral"
          variant="outline"
          :label="`Launched ${ch.launched}`"
        />
        <UBadge
          v-if="ch.closed"
          color="error"
          variant="subtle"
          :label="`Closed ${ch.closed}`"
        />
      </div>
      <p
        v-if="ch.alt_names?.length"
        class="text-sm text-muted"
      >
        Also known as {{ ch.alt_names.join(', ') }}
      </p>
      <p
        v-if="ch.replaced_by"
        class="text-sm"
      >
        Replaced by
        <ULink
          :to="channelLink(ch.replaced_by)"
          class="font-mono text-primary"
        >{{ ch.replaced_by }}</ULink>
      </p>
      <div class="flex flex-wrap gap-2 pt-1">
        <UButton
          v-if="ch.website"
          :to="ch.website"
          target="_blank"
          rel="noopener nofollow"
          icon="i-lucide-external-link"
          label="Website"
          color="neutral"
          variant="outline"
          size="sm"
        />
        <UButton
          :to="`https://iptv-org.github.io/?q=${encodeURIComponent(ch.id)}`"
          target="_blank"
          icon="i-lucide-tv"
          label="View on iptv-org"
          color="neutral"
          variant="outline"
          size="sm"
        />
      </div>
    </div>

    <section>
      <h3 class="mb-3 text-lg font-semibold text-highlighted">
        Channel logo
      </h3>
      <LogoTiles :channel="ch" />
    </section>

    <section v-if="editions.length">
      <h3 class="text-lg font-semibold text-highlighted">
        Editions
      </h3>
      <p class="mb-3 text-sm text-muted">
        Regional or local versions of the channel (iptv-org feeds). An edition without its own logo uses the channel logo.
      </p>
      <div class="space-y-2">
        <EditionRow
          v-for="f in editions"
          :key="f.id"
          :channel="ch"
          :feed="f"
        />
      </div>
    </section>

    <section>
      <h3 class="text-lg font-semibold text-highlighted">
        TV guide IDs
      </h3>
      <p class="mb-3 text-sm text-muted">
        IDs that TV guides (EPG) use for this channel when they differ from the iptv-org ID.
      </p>
      <UTable
        v-if="ch.aliases.length"
        :data="ch.aliases"
        :columns="aliasColumns"
        class="rounded-lg border border-default"
      >
        <template #epg_id-cell="{ row }">
          <span class="font-mono">{{ row.original.epg_id }}</span>
        </template>
        <template #feed-cell="{ row }">
          {{ row.original.feed || 'channel' }}
        </template>
        <template #actions-cell="{ row }">
          <UButton
            :to="forms.aliasRemove(ch.id, row.original)"
            target="_blank"
            label="Remove"
            color="error"
            variant="ghost"
            size="xs"
          />
        </template>
      </UTable>
      <p
        v-else
        class="text-sm text-muted"
      >
        None yet.
      </p>
      <UButton
        :to="forms.aliasAdd(ch.id)"
        target="_blank"
        icon="i-lucide-link"
        label="Add a guide ID"
        color="neutral"
        variant="outline"
        size="sm"
        class="mt-3"
      />
    </section>
  </div>
</template>
