<script setup lang="ts">
// The preparation of a logo on real files of the repository: a JPEG on white becomes a transparent PNG, and a logo
// with dark parts gets a white version for dark screens.
const { app } = useRuntimeConfig()
const base = `${SITE}logos`
</script>

<template>
  <div class="grid gap-4 sm:grid-cols-2">
    <figure class="space-y-2">
      <div class="flex aspect-[16/9] items-center justify-center rounded-xl bg-white p-6 ring-1 ring-default">
        <img
          :src="`${app.baseURL}showcase/telemadrid-source.jpg`"
          alt="Original file: a JPEG on a white background"
          class="max-h-full max-w-full object-contain"
        >
      </div>
      <figcaption class="flex items-center gap-2 text-sm text-muted">
        <UBadge
          label="1"
          color="neutral"
          variant="subtle"
          size="sm"
        />
        Source: JPEG on white, as found
      </figcaption>
    </figure>
    <figure class="space-y-2">
      <div class="bg-checker flex aspect-[16/9] items-center justify-center rounded-xl p-6 ring-1 ring-default">
        <img
          :src="`${base}/es/TelemadridINT.es.png`"
          alt="Published logo: transparent PNG"
          class="max-h-full max-w-full object-contain"
        >
      </div>
      <figcaption class="flex items-center gap-2 text-sm text-muted">
        <UBadge
          label="2"
          color="primary"
          variant="subtle"
          size="sm"
        />
        Published: background removed, trimmed
      </figcaption>
    </figure>
    <figure class="space-y-2">
      <div class="flex aspect-[16/9] items-center justify-center rounded-xl bg-tile-light p-6 ring-1 ring-default">
        <img
          :src="`${base}/fr/France3.fr.png`"
          alt="France 3 logo on a light background"
          class="max-h-full max-w-full object-contain"
        >
      </div>
      <figcaption class="flex items-center gap-2 text-sm text-muted">
        <UBadge
          label="3"
          color="primary"
          variant="subtle"
          size="sm"
        />
        On light screens: the logo itself
      </figcaption>
    </figure>
    <figure class="space-y-2">
      <div class="flex aspect-[16/9] items-center justify-center rounded-xl bg-tile-dark p-6 ring-1 ring-default">
        <img
          :src="`${base}/fr/France3.fr.white.png`"
          alt="France 3 white version on a dark background"
          class="max-h-full max-w-full object-contain"
        >
      </div>
      <figcaption class="flex items-center gap-2 text-sm text-muted">
        <UBadge
          label="4"
          color="secondary"
          variant="subtle"
          size="sm"
        />
        On dark screens: its white version
      </figcaption>
    </figure>
  </div>
</template>
