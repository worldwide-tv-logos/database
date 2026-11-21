// Website of worldwide-tv-logos (GitHub Pages), based on the Nuxt UI docs template.
// Its data (countries, channels, logos, logos.json, aliases.json) is built by `uv run logos export` into ../.api/:
// served as public files by `npm run dev`, and copied next to the generated pages by the deploy workflow.
// The pages fetch it in the browser; the list of countries gives the pages to prerender.
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const api = fileURLToPath(new URL('../.api', import.meta.url))
const countries: { code: string }[] = existsSync(`${api}/countries.json`)
  ? JSON.parse(readFileSync(`${api}/countries.json`, 'utf-8'))
  : []

export default defineNuxtConfig({
  modules: ['@nuxt/ui', '@nuxt/content'],

  devtools: { enabled: false },

  app: {
    head: {
      htmlAttrs: { lang: 'en' },
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: `${process.env.NUXT_APP_BASE_URL || '/'}favicon.svg` },
        { rel: 'apple-touch-icon', href: `${process.env.NUXT_APP_BASE_URL || '/'}apple-touch-icon.png` }
      ],
      meta: [
        { property: 'og:image', content: 'https://worldwide-tv-logos.github.io/database/og-image.png' },
        { property: 'og:image:width', content: '1200' },
        { property: 'og:image:height', content: '630' },
        { name: 'twitter:card', content: 'summary_large_image' },
        { name: 'theme-color', content: '#11141b' }
      ]
    }
  },

  css: ['~/assets/css/main.css'],

  colorMode: {
    preference: 'dark'
  },

  content: {
    build: { markdown: { toc: { searchDepth: 1 } } },
    experimental: { sqliteConnector: 'native' }
  },

  icon: {
    clientBundle: { scan: true, sizeLimitKb: 512 }
  },

  routeRules: {
    '/docs': { redirect: '/docs/getting-started' }
  },

  compatibilityDate: '2026-06-30',

  $development: {
    nitro: { publicAssets: existsSync(api) ? [{ dir: api, baseURL: '/', maxAge: 0 }] : [] }
  },

  nitro: {
    prerender: {
      crawlLinks: true,
      failOnError: false,
      routes: ['/', '/countries', ...countries.map(c => `/countries/${c.code}`)],
      ignore: [/\.(json|png)$/]
    }
  }
})
