# Page artwork

Source of every image in `screenshots/page/` and of the framed copies in `screenshots/framed/`.
The style follows the plugin: Neon glass with a rose-to-mint edge and sound-bar accents, and Cairo SemiBold for all text —
the same font used on the pages of every Ultra plugin, so the family reads as one.

```sh
npm i playwright && npx playwright install chromium   # once
node tools/page/build.js            # hero, headings, buttons, features, steps, family cards, colophon
node tools/page/build.js art hero   # only outputs whose name contains "hero"
node tools/page/build.js shots      # frame every screenshots/ua-tv-*.jpg into screenshots/framed/
```

New TV screenshots: add them to `screenshots/` as `ua-tv-….jpg`, run `shots`, and reference
the framed copy from the README. Original screenshots are never modified or removed.
