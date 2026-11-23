# Personal one-page website

A static personal website of a programmer: plain HTML, CSS and JavaScript — no frameworks, no
build step, no third-party code. Everything a visitor sees is in this repository.

## Run it locally

Open `index.html` in a browser. That is all the page needs.

Optionally, serve it over HTTP (correct MIME types, nicer URL):

```sh
python3 -m site_serve          # http://127.0.0.1:8080/  (or: make serve)
```

## Layout

```
index.html                     the whole page (hero, about, experience, skills, projects, contact)
assets/css/styles.css          design, dark/light themes, responsive rules, animations
assets/js/main.js              theme toggle, scroll reveal, profile photo swap
assets/img/favicon.svg         favicon (also used as the manifest icon)
assets/img/avatar-placeholder.svg  stand-in portrait until the owner's photo arrives
site.webmanifest               icon/theme metadata for deployment
site_serve.py                  optional local static server (not needed to view the page)
tests/                         checks of the page and of that server
```

## Content still to be provided by the owner

The biography text comes from the owner's CV, which has not been attached to the issue yet, so the
corresponding fields are placeholders marked `[...]` and `TODO(cv)`:

- name, job title/subtitle, summary, location
- experience entries (role, company, period, achievements)
- skill categories and skills
- projects (name, description, technologies)

Contact details are placeholders on purpose and stay plain text (no links, no form):

- e-mail address — `TODO(owner)` in `index.html`; obfuscate it against scraping bots when adding it
- LinkedIn profile URL — `TODO(owner)` in `index.html`; it stays text without an address until then

The profile photo is used automatically as soon as `assets/img/profile.jpg` is added (a square
image, 640×640 or larger is best). Until then a self-contained placeholder avatar is shown; the
circular crop (`.avatar__img`) is theme-aware, so the portrait reads correctly in dark and light.

## Design notes

- Dark theme is the default; the toggle stores the choice in `localStorage` and a `<head>` script
  applies it before the first paint. With no stored choice the OS preference is followed.
- Animations (section reveal on scroll, hover effects) live inside
  `@media (prefers-reduced-motion: no-preference)` and the `prefers-reduced-motion: reduce` block
  neutralises transitions, animations and smooth scrolling. With JavaScript disabled, sections are
  visible without animation.
- Responsive: single column on phones (sticky header with wrapping nav), two-column hero and
  card grids from `56rem` up.
- Meta data for deployment: `description`, `author`, `color-scheme`, `theme-color`, Open Graph and
  Twitter card tags, favicon, apple-touch icon and `site.webmanifest`.

## Deploying

Static files only — publish the repository root (or a copy of it) to any static host; there is
nothing to build. Before going public: replace the placeholders above, add `assets/img/profile.jpg`
and an `og:image`, and set `<link rel="canonical">` in `index.html`.

## Tests

```sh
make test     # pytest with coverage (dependencies only from requirements-dev.lock, with hashes)
make check    # node --check of the page's JavaScript, when node is available
```

`site_serve.py` is the only Python code in the repository and it is optional tooling: the page is
plain static files. It is tested so that CI keeps a real baseline (`.github/scripts/asome_ci.sh`
detects a Python project from `requirements-dev.lock`).
