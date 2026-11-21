<script setup lang="ts">
withDefaults(defineProps<{ code: string, name?: string, size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' }>(), {
  name: undefined,
  size: 'sm'
})
</script>

<template>
  <UAvatar
    :src="flagUrl(code)"
    :alt="name || code.toUpperCase()"
    :text="code.toUpperCase()"
    :size="size"
    loading="lazy"
    class="rounded-md ring-1 ring-default [&>img]:object-cover"
  />
</template>
