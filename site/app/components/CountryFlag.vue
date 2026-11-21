<script setup lang="ts">
// Flag as an image (emoji flags are not drawn on Windows). iptv-org uses UK where flag sets use GB.
const props = defineProps<{ code: string, name?: string }>()
const src = computed(() => `https://flagcdn.com/w80/${({ uk: 'gb' } as Record<string, string>)[props.code] || props.code}.png`)
const failed = ref(false)
</script>

<template>
  <img
    v-if="!failed"
    :src="src"
    :alt="''"
    :title="name"
    loading="lazy"
    class="inline-block h-[1em] w-auto rounded-[2px] shadow-sm ring-1 ring-default"
    @error="failed = true"
  >
</template>
