// Data of the website (built by `uv run logos export`) and helpers shared by the pages.

export interface Country {
  code: string
  name: string
  flag: string
  channels: number
  logos: number
}

export interface Logo {
  feed: string | null
  variant: string | null
  url: string
  width: number
  height: number
  updated: string
}

export interface Feed {
  id: string
  name: string
  is_main: boolean
  format: string | null
}

export interface Alias {
  epg_id: string
  source: string
  feed: string | null
}

export interface Channel {
  id: string
  name: string
  alt_names: string[] | null
  network: string | null
  categories: string[] | null
  website: string | null
  launched: string | null
  closed: string | null
  replaced_by: string | null
  feeds: Feed[]
  logos: Logo[]
  aliases: Alias[]
}

export interface CountryData {
  code: string
  name: string
  flag: string
  channels: Channel[]
}

/** [id, name, country code, number of logos] */
export type SearchRow = [string, string, string, number]

export const REPO = 'https://github.com/worldwide-tv-logos/database'
export const SITE = 'https://worldwide-tv-logos.github.io/database/'

/** JSON file of the website data, fetched in the browser (the pages are static). */
export function useApiFile<T>(path: MaybeRefOrGetter<string>, options: { immediate?: boolean } = {}) {
  const { app } = useRuntimeConfig()
  return useFetch<T>(() => toValue(path), {
    baseURL: app.baseURL,
    server: false,
    key: `api:${toValue(path)}`,
    ...options
  })
}

/** Lowercase text without accents, for filters. */
export function fold(s: string | null | undefined): string {
  return String(s ?? '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

export function logoId(channel: string, feed?: string | null): string {
  return feed ? `${channel}@${feed}` : channel
}

/** Country of a channel ID (`TF1.fr` -> `fr`). */
export function countryOf(id: string): string {
  return id.split('@')[0]!.split('.').pop()!.toLowerCase()
}

export function channelLink(id: string) {
  return { path: `/countries/${countryOf(id)}`, query: { channel: id } }
}

/** Quality versions of a channel (TF1@HD) always use the channel logo (same rule as the harvest). */
export const QUALITY_FEED = /^(SD|HD|FHD|UHD|QHD|4K|8K|HDR|H265|HEVC|1080p?|720p?)$/i

export function mainLogo(ch: Channel, feed: string | null = null): Logo | undefined {
  return ch.logos.find(l => (l.feed || null) === feed && !l.variant)
}

export function whiteLogo(ch: Channel, feed: string | null = null): Logo | undefined {
  return ch.logos.find(l => (l.feed || null) === feed && l.variant === 'white')
}

/** Logo to show on a dark tile: the white variant when there is one. */
export function darkLogo(ch: Channel, feed: string | null = null): Logo | undefined {
  return whiteLogo(ch, feed) || mainLogo(ch, feed)
}

/** Logo shown on a channel card: its own, else the one of any edition. */
export function cardLogo(ch: Channel): Logo | undefined {
  return darkLogo(ch) || ch.logos.find(x => x.variant === 'white') || ch.logos.find(x => !x.variant)
}

function form(template: string, fields: Record<string, string>): string {
  return `${REPO}/issues/new?${new URLSearchParams({ template, ...fields }).toString()}`
}

function ids(c: string, f?: string | null): Record<string, string> {
  return { channel_id: c, ...(f ? { feed_id: f } : {}) }
}

/** Issue forms, prefilled with the channel and the edition. */
export const forms = {
  add: (c: string, f?: string | null) => form('01_logos_add.yml', { title: `Add logo: ${logoId(c, f)}`, ...ids(c, f) }),
  edit: (c: string, f?: string | null) => form('02_logos_edit.yml', { title: `Edit logo: ${logoId(c, f)}`, ...ids(c, f) }),
  remove: (c: string, f?: string | null) => form('03_logos_remove.yml', { title: `Remove logo: ${logoId(c, f)}`, ...ids(c, f) }),
  request: (c: string, f?: string | null) => form('04_logos_request.yml', { title: `Logo wanted: ${logoId(c, f)}`, ...ids(c, f) }),
  aliasAdd: (c: string, f?: string | null) => form('05_aliases_add.yml', { title: `Alias: ${logoId(c, f)}`, ...ids(c, f) }),
  aliasRemove: (c: string, a: Alias) => form('06_aliases_remove.yml', {
    title: `Remove alias: ${a.source}:${a.epg_id}`, epg_id: a.epg_id, epg_source: a.source, ...ids(c, a.feed)
  })
}
