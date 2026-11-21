// Links of the first website used hash routes: #/api, #/<cc>, #/<cc>/<channel id>. They keep working.
export default defineNuxtPlugin(() => {
  const hash = window.location.hash
  if (!hash.startsWith('#/')) return
  const parts = hash.slice(2).split('/').filter(Boolean).map(decodeURIComponent)
  let to: string | { path: string, query?: Record<string, string> } = '/'
  if (parts[0] === 'api') to = '/docs/getting-started/api'
  else if (parts.length >= 2) to = { path: `/countries/${parts[0]!.toLowerCase()}`, query: { channel: parts.slice(1).join('/') } }
  else if (parts.length === 1) to = `/countries/${parts[0]!.toLowerCase()}`
  navigateTo(to, { replace: true })
})
