<script setup lang="ts">
// The mark (same drawing as public/logo-mark.svg) and the name, written in the site font so that it follows the theme.
const id = useId()
</script>

<template>
  <span class="inline-flex items-center gap-2.5 font-semibold tracking-tight text-highlighted">
    <svg
      viewBox="0 0 48 32"
      fill="none"
      class="h-7 w-auto shrink-0"
      aria-hidden="true"
    >
      <defs>
        <linearGradient
          :id="id"
          x1="0"
          y1="0"
          x2="48"
          y2="0"
          gradientUnits="userSpaceOnUse"
        >
          <stop
            offset="0"
            stop-color="#00B4F4"
          />
          <stop
            offset="0.5"
            stop-color="#0765F7"
          />
          <stop
            offset="1"
            stop-color="#8323F5"
          />
        </linearGradient>
      </defs>
      <g
        :stroke="`url(#${id})`"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <rect
          x="1.6"
          y="1.6"
          width="44.8"
          height="28.8"
          rx="6.8"
          stroke-width="3.2"
        />
        <g stroke-width="2">
          <circle
            cx="24"
            cy="16"
            r="11"
          />
          <path d="M24 5Q15 16 24 27Q33 16 24 5Z" />
          <path d="M13 16h22" />
        </g>
      </g>
    </svg>
    <span class="text-[17px]">Worldwide TV Logos</span>
  </span>
</template>
