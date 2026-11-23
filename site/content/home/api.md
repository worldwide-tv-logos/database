::code-group

```txt [URL]
# base: https://worldwide-tv-logos.github.io/database/
logos/ch_1r840gxdj5.png         # France 3, light screens
logos/ch_1r840gxdj5.white.png   # France 3, dark screens
logos/ch_dhk02zjhwa.png         # France 3 Alsace, an edition
```

```js [JavaScript]
const base = 'https://worldwide-tv-logos.github.io/database/'
const logos = await (await fetch(`${base}logos.json`)).json()

const logo = (iptv, { dark = false } = {}) =>
  logos.find(l => l.iptv === iptv && (l.variant === 'white') === dark)
  ?? logos.find(l => l.iptv === iptv)

logo('France3.fr', { dark: true }).url
```

```bash [curl]
curl -s https://worldwide-tv-logos.github.io/database/logos.json \
  | jq -r '.[] | select(.iptv == "France3.fr" and .variant == null) | .url'
```

::
