<script setup lang="ts">
const { app } = useRuntimeConfig()
const files = ['channels.json', 'logos.json', 'guides.json']
</script>

<template>
  <UFooter>
    <template #left>
      <p>
        Channels and IDs from
        <ULink
          to="https://github.com/iptv-org/database"
          target="_blank"
          class="text-primary"
        >iptv-org</ULink>.
        JSON:
        <template v-for="(file, i) in files" :key="file">
          <ULink
            :to="`${app.baseURL}${file}`"
            external
            class="text-primary"
          >{{ file }}</ULink>{{ i < files.length - 1 ? ', ' : '.' }}
        </template>
      </p>
    </template>

    <template #right>
      <UButton
        icon="i-simple-icons-github"
        to="https://github.com/worldwide-tv-logos/database"
        target="_blank"
        color="neutral"
        variant="ghost"
        aria-label="GitHub"
      />
    </template>
  </UFooter>
</template>
