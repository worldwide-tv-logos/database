import { defineContentConfig, defineCollection, z } from '@nuxt/content'

export default defineContentConfig({
  collections: {
    // pieces of the home page written in Markdown (code examples)
    home: defineCollection({
      type: 'page',
      source: 'home/**'
    }),
    docs: defineCollection({
      type: 'page',
      source: 'docs/**',
      schema: z.object({
        links: z.array(z.object({
          label: z.string(),
          icon: z.string(),
          to: z.string(),
          target: z.string().optional()
        })).optional()
      })
    })
  }
})
