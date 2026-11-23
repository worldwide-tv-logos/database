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
  slug: string
  country: string
  closed: boolean
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
  slug: string
  iptv: string | null
  country: string
  name: string
  alt_names: string[] | null
  network: string | null
  categories: string[] | null
  website: string | null
  launched: string | null
  closed: string | null
  replaced_by: string | null
  replaced_by_country: string | null
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

/** [id, name, country code, number of logos, other IDs: iptv-org, Wikidata, TV guides, editions] */
export type SearchRow = [string, string, string, number, string?]

/** One record of logos.json (the public API). */
export interface ApiLogo {
  channel: string
  slug: string | null
  iptv: string | null
  parent: string | null
  variant: string | null
  url: string
  width: number
  height: number
  country: string
  updated: string
}

/** Flag image of a country (iptv-org uses UK where flag sets use GB). */
export function flagUrl(code: string): string {
  return `https://flagcdn.com/w80/${({ uk: 'gb' } as Record<string, string>)[code] || code}.png`
}

/** Channels of the search index matching a term: name or ID, without accents; channels with a logo first. */
export function searchChannels(index: SearchRow[] | null | undefined, term: string, limit = 20): SearchRow[] {
  const t = fold(term.trim())
  if (t.length < 2 || !index) return []
  const out: SearchRow[] = []
  for (const row of index) {
    if (fold(row[1]).includes(t) || row[0].toLowerCase().includes(t) || (row[4] ?? '').toLowerCase().includes(t)) out.push(row)
    if (out.length >= limit * 3) break
  }
  return out.sort((a, b) => Number(b[3] > 0) - Number(a[3] > 0)).slice(0, limit)
}

export const REPO = 'https://github.com/worldwide-tv-logos/database'
export const SITE = 'https://worldwide-tv-logos.github.io/database/'

/** JSON file of the website data, fetched in the browser (the pages are static). The build ID of the deployment is
 * added to the address: a browser never mixes data cached from an older deployment with the current pages. */
export function useApiFile<T>(path: MaybeRefOrGetter<string>, options: { immediate?: boolean } = {}) {
  const { app } = useRuntimeConfig()
  return useFetch<T>(() => toValue(path), {
    baseURL: app.baseURL,
    query: { v: app.buildId },
    server: false,
    key: `api:${toValue(path)}`,
    ...options
  })
}

/** Lowercase text without accents, for filters. */
export function fold(s: string | null | undefined): string {
  return String(s ?? '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/** Our ID of a channel, or of one of its editions. */
export function logoId(channel: string, feed?: string | null): string {
  return feed || channel
}

export function channelLink(id: string, cc: string) {
  return { path: `/countries/${cc.toLowerCase()}`, query: { channel: id } }
}

/** Quality and timeshift versions of a channel (TF1@HD, Boomerang@Plus1) always use the channel logo (same rule as the harvest). */
export const QUALITY_FEED = /^(SD|HD|FHD|UHD|QHD|4K|8K|HDR|H265|HEVC|1080p?|720p?|Plus\d+)$/i

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
  return { channel_id: f || c }
}

/** Issue forms, prefilled with the channel and the edition. */
export const forms = {
  add: (c: string, f?: string | null) => form('01_logos_add.yml', { title: `Add logo: ${logoId(c, f)}`, ...ids(c, f) }),
  edit: (c: string, f?: string | null) => form('02_logos_edit.yml', { title: `Edit logo: ${logoId(c, f)}`, ...ids(c, f) }),
  remove: (c: string, f?: string | null) => form('03_logos_remove.yml', { title: `Remove logo: ${logoId(c, f)}`, ...ids(c, f) }),
  request: (c: string, f?: string | null) => form('04_logos_request.yml', { title: `Logo wanted: ${logoId(c, f)}`, ...ids(c, f) }),
  aliasAdd: (c: string, f?: string | null) => form('05_aliases_add.yml', { title: `Alias: ${logoId(c, f)}`, ...ids(c, f) }),
  channelAdd: (cc: string) => form('07_channels_add.yml', { title: 'Add channel: ', country: cc }),
  aliasRemove: (c: string, a: Alias) => form('06_aliases_remove.yml', {
    title: `Remove alias: ${a.source}:${a.epg_id}`, epg_id: a.epg_id, epg_source: a.source, ...ids(c, a.feed)
  })
}
