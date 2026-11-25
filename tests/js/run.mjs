/**
 * Behaviour tests of assets/js/main.js, run under plain node (`node tests/js/run.mjs page-tree.json`).
 * The element tree comes from the real index.html (parsed to JSON by tests/test_page_js.py), so the
 * page script never runs against invented markup.
 * Exit code: number of failed checks.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createEnvironment } from "./dom.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const tree = JSON.parse(readFileSync(process.argv[2], "utf8"));
const pageScript = readFileSync(join(root, "assets", "js", "main.js"), "utf8");
const headScript = tree.children
  .find((node) => node.tag === "head")
  .children.filter((node) => node.tag === "script")
  .map((node) => (node.children ?? []).filter((child) => "text" in child).map((child) => child.text).join(""))
  .join("\n");

let failures = 0;
function check(name, condition, detail) {
  if (condition) {
    console.log(`ok   ${name}`);
  } else {
    failures += 1;
    console.log(`FAIL ${name}${detail === undefined ? "" : ` — got ${JSON.stringify(detail)}`}`);
  }
}

/** A recorded IntersectionObserver stand-in: the test drives the callback itself. */
function recordingObserver(instances) {
  return function Observer(callback, options) {
    this.callback = callback;
    this.options = options;
    this.targets = [];
    instances.push(this);
    this.observe = (target) => this.targets.push(target);
    this.unobserve = (target) => {
      this.targets = this.targets.filter((item) => item !== target);
    };
    this.report = (targets = this.targets) =>
      this.callback(targets.map((target) => ({ isIntersecting: true, target })), this);
  };
}

/**
 * Fresh environment with the real page: the inline <head> theme script and assets/js/main.js,
 * each in its own scope the way a browser runs them.
 */
function load({ env: envOptions = {}, head = true, stored, globals = {} } = {}) {
  const env = createEnvironment({ tree, ...envOptions });
  if (stored !== undefined) {
    // what a previous visit would have left in localStorage, seeded before the head script runs
    env.window.localStorage.setItem("theme", stored);
  }
  if (head) {
    new Function("document", "localStorage", headScript)(env.document, env.window.localStorage);
  }
  // main.js reaches the observer through `window`, so the stand-ins go onto the window object
  Object.assign(env.window, globals);
  const parameters = {
    document: env.document,
    window: env.window,
    localStorage: env.window.localStorage,
    Image: env.window.Image,
    IntersectionObserver: env.window.IntersectionObserver,
  };
  new Function(...Object.keys(parameters), `"use strict";\n${pageScript}`)(...Object.values(parameters));
  return env;
}

const themeOf = (env) => env.document.documentElement.getAttribute("data-theme");
const labelOf = (button) => button.querySelector(".theme-toggle__label")?.textContent;

// 1. dark is the default and the toggle switches to light and back
{
  const env = load();
  const button = env.document.getElementById("theme-toggle");
  check("toggle button found in the real markup", !!button);
  check("default theme is dark", themeOf(env) === "dark", themeOf(env));
  check("button starts not pressed", button.getAttribute("aria-pressed") === "false");
  check("button announces light as next", button.getAttribute("aria-label") === "Switch to light theme");
  check("label shows the current theme", labelOf(button) === "Dark", labelOf(button));

  button.dispatchEvent({ type: "click" });
  check("click switches to light", themeOf(env) === "light", themeOf(env));
  check("pressed reflects light", button.getAttribute("aria-pressed") === "true");
  check("button announces dark as next", button.getAttribute("aria-label") === "Switch to dark theme");
  check("label follows the theme", labelOf(button) === "Light", labelOf(button));
  check("title follows the theme", button.getAttribute("title") === "Switch to dark theme");
  check("choice is stored", env.window.localStorage.getItem("theme") === "light");

  button.dispatchEvent({ type: "click" });
  check("second click returns to dark", themeOf(env) === "dark", themeOf(env));
  check("storage updated", env.window.localStorage.getItem("theme") === "dark");
  check("unpressed again", button.getAttribute("aria-pressed") === "false");
}

// 2. the inline <head> script restores a stored choice before the first paint
{
  const env = load({ stored: "light" });
  check("stored light wins over the dark default", themeOf(env) === "light", themeOf(env));
}
{
  const env = load({ stored: "nonsense" });
  check("an unusable stored value keeps the default", themeOf(env) === "dark", themeOf(env));
}

// 3. broken localStorage (private mode) must not break the toggle
{
  const env = load({ env: { storageFailing: true } });
  const button = env.document.getElementById("theme-toggle");
  let threw = false;
  try {
    button.dispatchEvent({ type: "click" });
  } catch (err) {
    threw = String(err);
  }
  check("toggle works without storage", !threw && themeOf(env) === "light", threw || themeOf(env));
}

// 4. the OS preference is followed only while the visitor has not chosen
{
  const env = load();
  const osQuery = env.mediaQueries.find((query) => /prefers-color-scheme/.test(query.query));
  check("the page listens for the OS colour scheme", !!osQuery, env.mediaQueries.map((q) => q.query));
  osQuery.emit(true);
  check("OS light is adopted with no stored choice", themeOf(env) === "light", themeOf(env));

  const chosen = load({ stored: "dark" });
  chosen.document.getElementById("theme-toggle").dispatchEvent({ type: "click" });
  chosen.mediaQueries.find((query) => /prefers-color-scheme/.test(query.query)).emit(false);
  check("a chosen theme survives an OS change", themeOf(chosen) === "light", themeOf(chosen));
}

// 5. scroll reveal: hidden until intersecting, then revealed and unobserved
{
  const plain = load();
  const sections = plain.document.querySelectorAll("[data-reveal]");
  check("every section opts into reveal", sections.length >= 6, sections.length);
  check("sections start hidden", sections.every((node) => !node.classList.contains("is-visible")));

  const instances = [];
  const env = load({ globals: { IntersectionObserver: recordingObserver(instances) } });
  const instance = instances[0];
  const revealed = env.document.querySelectorAll("[data-reveal]");
  check("one observer per page", instances.length === 1, instances.length);
  check("every section is observed", instance.targets.length === revealed.length, instance.targets.length);
  check("threshold is not zero", instance.options.threshold > 0, instance.options);
  check("root margin pulls the trigger early", /-/.test(instance.options.rootMargin), instance.options);

  instance.report([instance.targets[0]]);
  check("an intersecting section reveals", revealed[0].classList.contains("is-visible"));
  check("the rest stays hidden", revealed.slice(1).every((node) => !node.classList.contains("is-visible")));
  check("a revealed section is unobserved", !instance.targets.includes(revealed[0]), instance.targets.length);
  instance.report();
  check("all sections reveal once visible", revealed.every((node) => node.classList.contains("is-visible")));
}

// 6. reduced motion: everything visible immediately, no observer at all
{
  const instances = [];
  const env = load({
    env: { reducedMotion: true },
    globals: { IntersectionObserver: recordingObserver(instances) },
  });
  const sections = env.document.querySelectorAll("[data-reveal]");
  check("reduced motion reveals at once", sections.length > 0 && sections.every((node) => node.classList.contains("is-visible")));
  check("reduced motion uses no observer", instances.length === 0, instances.length);
}

// 7. no IntersectionObserver support: the page is still readable
{
  const env = load({ globals: { IntersectionObserver: undefined } });
  const sections = env.document.querySelectorAll("[data-reveal]");
  check("sections visible without IntersectionObserver",
    sections.length > 0 && sections.every((node) => node.classList.contains("is-visible")));
}

// 8. the safety timer force-reveals sections already on screen
{
  const instances = [];
  const env = load({ globals: { IntersectionObserver: recordingObserver(instances) } });
  const timer = env.timers.at(-1);
  check("a safety timer is scheduled", !!timer && timer.delay > 0, env.timers);
  const pending = [];
  const offscreen = load({
    env: { onScreen: false },
    globals: { IntersectionObserver: recordingObserver(pending) },
  });
  check("an off-screen section is still pending",
    offscreen.document.querySelectorAll("[data-reveal]").every((node) => !node.classList.contains("is-visible")));
  offscreen.flushTimers();
  check("the timer leaves off-screen sections hidden",
    offscreen.document.querySelectorAll("[data-reveal]").every((node) => !node.classList.contains("is-visible")));
  env.flushTimers();
  const sections = env.document.querySelectorAll("[data-reveal]");
  check("on-screen sections are force-revealed", sections.every((node) => node.classList.contains("is-visible")));
  check("force-revealed sections stop being observed", instances[0].targets.length === 0, instances[0].targets.length);
}

// 9. profile photo swap
{
  const env = load();
  const probe = env.probes.at(-1);
  check("photo probe targets the owner file", probe?._src === "assets/img/profile.jpg", probe?._src);
  const avatar = env.document.querySelector(".avatar__img");
  const original = avatar.getAttribute("src");
  probe.settle(true);
  check("real photo used when it loads", avatar.getAttribute("src") === "assets/img/profile.jpg", avatar.getAttribute("src"));
  check("photo marked on the element", avatar.getAttribute("data-photo") === "owner");

  const missing = load();
  const missingAvatar = missing.document.querySelector(".avatar__img");
  const fallback = missingAvatar.getAttribute("data-photo-fallback");
  check("fallback attribute points at a placeholder", Boolean(fallback), fallback);
  missing.probes.at(-1).settle(false);
  check("placeholder kept when the photo is missing", missingAvatar.getAttribute("src") === original, missingAvatar.getAttribute("src"));
  check("no stale photo marker", !missingAvatar.hasAttribute("data-photo"));
}

// 10. footer year
{
  const env = load();
  const node = env.document.getElementById("year");
  check("footer year filled with the current year", node.textContent === String(new Date().getFullYear()), node.textContent);
}

console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
process.exit(failures ? 1 : 0);
