# ASHP Midyear 2026 Touch Kiosks

## → **https://bstewart-svg.github.io/ashp-kiosk/**

HTML versions of Riley Moody's five ASHP Midyear 2026 kiosk decks. Each deck has its own URL
and its own offline cache, so every kiosk runs just the deck it's showing:

| Deck | URL |
|---|---|
| Axona (7 slides) | https://bstewart-svg.github.io/ashp-kiosk/axona/ |
| Clinic (4 slides) | https://bstewart-svg.github.io/ashp-kiosk/clinic/ |
| Home (9 slides) | https://bstewart-svg.github.io/ashp-kiosk/home/ |
| Hospital (5 slides) | https://bstewart-svg.github.io/ashp-kiosk/hospital/ |
| Retail (5 slides) | https://bstewart-svg.github.io/ashp-kiosk/retail/ |

**Built in layers, not screenshots.** Every text box, shape, line, icon and photo from the
PowerPoint is its own HTML/SVG element, positioned to the deck's exact coordinates on a
1920 × 1080 stage that scales to any screen. Text is live, set in the deck's own fonts
(Archivo Expanded / SemiExpanded, Funnel Sans, IBM Plex Mono, Barlow), which are bundled
in `fonts/`, so it renders the same on Windows, Android, macOS and ChromeOS.

**Touch behaviour**
- Autoplay starts on load and uses each slide's own timing from the deck (5 to 14 s),
  looping back to the first slide.
- Tap the right half of the screen to go forward and the left half to go back, or swipe.
- The control pill at bottom centre has Back, Play / Pause, slide dots and Next. It dims
  when nobody is touching it.
- Any manual navigation pauses autoplay. After 45 s with nobody touching it, autoplay resumes.

**Motion:** slides crossfade (the deck's own fade transition). On each slide, the content
fades in with a 14 px upward drift, staggered in reading order. Full-bleed photos zoom
3.5% over 16 s. Background art (blooms, scrims, striations) fades with the slide and
doesn't animate separately. Motion is turned off for devices set to reduce motion.

---

## Setting up a kiosk

1. While online, open the deck's URL **once** with `?cache` on the end, for example
   `https://bstewart-svg.github.io/ashp-kiosk/home/?cache`.
   A readout at the top turns green at `CACHED — RUNS OFFLINE (NN FILES)`.
2. From then on the deck runs with **no internet**. Whenever the kiosk is online again it
   picks up the latest version on its own. Use the URL without `?cache` for the show.
3. Full screen:
   - **Windows:** run Edge in kiosk mode, for example from a shortcut in the Startup folder:
     ```
     msedge.exe --kiosk "https://bstewart-svg.github.io/ashp-kiosk/home/" --edge-kiosk-type=fullscreen --no-first-run
     ```
     Use the same Windows user and browser profile every time, because the offline copy
     lives in that profile.
   - **Android panels:** set the URL as the Start URL in Fully Kiosk Browser, and turn on
     Keep Screen On, Hardware Acceleration and Kiosk Mode.

Clearing browsing data removes the offline copy. If that happens, repeat step 1 while online.

The site is public, but it carries `noindex,nofollow` and a `robots.txt` deny, so it won't
appear in search results.

---

## Updating

When Riley updates a deck, put the new `.pptx` files in `_src/` (git-ignored) and rebuild:

```
python3 tools/build.py . <fonts-dir> "axona:Axona:_src/axona" "clinic:Clinic:_src/clinic" ...
```

Each `_src/<deck>` is the unzipped `.pptx`. `tools/convert.py` reads the slide XML
(shapes, text, pictures, groups, gradients, crops and timings) and writes the layered HTML.
`tools/build.py` assembles each deck's `index.html` and `sw.js`. The cache version in each
`sw.js` is a hash of that deck's media, so kiosks pick up replaced images automatically.

Small copy fixes can also be made by hand directly in `<deck>/index.html`. Every text run is
plain HTML.

```
index.html          deck picker
<deck>/index.html   the slides (layered HTML/SVG), styles and player logic
<deck>/sw.js        offline cache for that deck
<deck>/media/       the deck's photos, logos and SVG icons
fonts/              Archivo, Funnel Sans, IBM Plex Mono, Barlow (woff2)
tools/              converter and build scripts
```
