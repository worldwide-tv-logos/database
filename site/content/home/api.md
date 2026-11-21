::code-group

```txt [URL]
# base: https://worldwide-tv-logos.github.io/database/
logos/fr/France3.fr.png         # light screens
logos/fr/France3.fr.white.png   # dark screens
logos/fr/France3.fr@Alsace.png  # an edition
```

```js [JavaScript]
const base = 'https://worldwide-tv-logos.github.io/database/'
const logos = await (await fetch(`${base}logos.json`)).json()

const logo = (channel, { dark = false } = {}) =>
  logos.find(l => l.channel === channel && !l.feed && (l.variant === 'white') === dark)
  ?? logos.find(l => l.channel === channel && !l.feed)

logo('France3.fr', { dark: true }).url
```

```bash [curl]
curl -s https://worldwide-tv-logos.github.io/database/logos.json \
  | jq -r '.[] | select(.channel == "France3.fr" and .variant == null) | .url'
```

::
