<script setup lang="ts">
const { app } = useRuntimeConfig()
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
        <ULink
          :to="`${app.baseURL}logos.json`"
          external
          class="text-primary"
        >logos.json</ULink>,
        <ULink
          :to="`${app.baseURL}aliases.json`"
          external
          class="text-primary"
        >aliases.json</ULink>.
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
