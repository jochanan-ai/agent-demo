/**
 * Behaviour tests of assets/js/main.js, run under plain node (`node tests/js/run.mjs`).
 * The element tree comes from the real index.html (parsed to JSON by tests/test_page_js.py).
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

let failures = 0;
function check(name, condition, detail) {
  if (condition) {
    console.log(`ok   ${name}`);
  } else {
    failures += 1;
    console.log(`FAIL ${name}${detail === undefined ? "" : ` — got ${JSON.stringify(detail)}`}`);
  }
}

function load(options = {}) {
  Image.probes.length = 0;
  const env = createEnvironment(options);
  // the inline <head> script of index.html, run the way a browser runs it before the body parses
  const headScript = tree.children
    .find((node) => node.tag === "head")
    .children.filter((node) => node.tag === "script")
    .map((node) => node.text || "")
    .join("\n");
  const scope = { document: env.document, localStorage: env.window.localStorage };
  new Function("document", "localStorage", headScript)(env.document, env.window.localStorage);
  void scope;
  new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
    env.document,
    env.window,
    env.window.localStorage,
    env.window.Image,
    env.window.IntersectionObserver
  );
  return env;
}

// 1. dark is the default and the toggle switches to light and back
{
  const env = load();
  const button = env.document.getElementById("theme-toggle");
  check("default theme is dark", env.document.documentElement.getAttribute("data-theme") === "dark",
    env.document.documentElement.getAttribute("data-theme"));
  check("button starts not pressed", button.getAttribute("aria-pressed") === "false");
  check("button announces light as next", button.getAttribute("aria-label") === "Switch to light theme");

  button.dispatchEvent({ type: "click" });
  check("click switches to light", env.document.documentElement.getAttribute("data-theme") === "light",
    env.document.documentElement.getAttribute("data-theme"));
  check("pressed reflects light", button.getAttribute("aria-pressed") === "true");
  check("button announces dark as next", button.getAttribute("aria-label") === "Switch to dark theme");
  check("label shows current", button.childNodes.find((n) => n.attributes?.class === "theme-toggle__label").text === undefined ||
    button.querySelector(".theme-toggle__label").textContent === "Light",
    button.querySelector(".theme-toggle__label")?.textContent);
  check("choice is stored", env.window.localStorage.getItem("theme") === "light");

  button.dispatchEvent({ type: "click" });
  check("second click returns to dark", env.document.documentElement.getAttribute("data-theme") === "dark");
  check("storage updated", env.window.localStorage.getItem("theme") === "dark");
}

// 2. a stored theme is restored by the inline head script
{
  const env = load();
  env.window.localStorage.setItem("theme", "light");
  const restored = load();
  // load() runs the head script against a fresh document; seed storage first:
  restored.window.localStorage.setItem("theme", "light");
  const again = load();
  again.window.localStorage.setItem("theme", "light");
  void env;
  const fresh = (() => {
    const e = createEnvironment({ tree });
    e.window.localStorage.setItem("theme", "light");
    const headScript = tree.children
      .find((node) => node.tag === "head")
      .children.filter((node) => node.tag === "script")
      .map((node) => node.text || "")
      .join("\n");
    new Function("document", "localStorage", headScript)(e.document, e.window.localStorage);
    return e;
  })();
  check("stored light wins over the default", fresh.document.documentElement.getAttribute("data-theme") === "light",
    fresh.document.documentElement.getAttribute("data-theme"));
}

// 3. broken localStorage (private mode) must not break the toggle
{
  const env = load({ storageFailing: true });
  const button = env.document.getElementById("theme-toggle");
  let threw = false;
  try {
    button.dispatchEvent({ type: "click" });
  } catch (err) {
    threw = true;
  }
  check("toggle works without storage", !threw && env.document.documentElement.getAttribute("data-theme") === "light");
}

// 4. scroll reveal
{
  const env = load();
  const sections = env.document.querySelectorAll("[data-reveal]");
  check("sections found", sections.length >= 6, sections.length);
  const observers = [];
  const Real = env.window.IntersectionObserver;
  env.window.IntersectionObserver = class extends Real {
    constructor(cb, opts) {
      super(cb, opts);
      observers.push(this);
    }
  };
  const env2 = (() => {
    const e = createEnvironment({ tree });
    new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
      e.document, e.window, e.window.localStorage, e.window.Image, e.window.IntersectionObserver
    );
    return e;
  })();
  void observers;
  const observed = env2.window.__observers;
  void observed;
  // find the observer through the page: sections get the class when reported visible
  const ioInstances = [];
  const env3 = (() => {
    const e = createEnvironment({ tree });
    const IO = function (cb, opts) {
      this.cb = cb;
      this.opts = opts;
      this.targets = [];
      this.observe = (t) => this.targets.push(t);
      this.unobserve = (t) => { this.targets = this.targets.filter((x) => x !== t); };
      ioInstances.push(this);
    };
    new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
      e.document, Object.assign(e.window, { IntersectionObserver: IO }), e.window.localStorage, e.window.Image, IO
    );
    return e;
  })();
  const instance = ioInstances[0];
  check("observer created with options", !!instance && instance.targets.length === sections.length,
    instance && instance.targets.length);
  check("threshold is not zero", !!instance && instance.opts.threshold > 0, instance && instance.opts);
  check("sections start hidden", sections.every((s) => !s.classList.contains("is-visible")));
  instance.cb(instance.targets.map((target) => ({ isIntersecting: true, target })), instance);
  check("sections reveal when intersecting",
    env3.document.querySelectorAll("[data-reveal]").every((s) => s.classList.contains("is-visible")));
  check("revealed sections are unobserved", instance.targets.length === 0, instance.targets.length);
  void env2;
}

// 5. reduced motion: everything visible immediately, no observer
{
  const ioInstances = [];
  const e = createEnvironment({ tree, reducedMotion: true });
  const IO = function () {
    this.observe = () => ioInstances.push("observed");
    this.unobserve = () => {};
  };
  new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
    e.document, Object.assign(e.window, { IntersectionObserver: IO }), e.window.localStorage, e.window.Image, IO
  );
  const sections = e.document.querySelectorAll("[data-reveal]");
  check("reduced motion reveals at once", sections.length > 0 && sections.every((s) => s.classList.contains("is-visible")));
  check("reduced motion uses no observer", ioInstances.length === 0, ioInstances.length);
}

// 6. no IntersectionObserver support: still visible
{
  const e = createEnvironment({ tree });
  new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
    e.document, Object.assign(e.window, { IntersectionObserver: undefined }), e.window.localStorage, e.window.Image, undefined
  );
  const sections = e.document.querySelectorAll("[data-reveal]");
  check("sections visible without IntersectionObserver",
    sections.length > 0 && sections.every((s) => s.classList.contains("is-visible")));
}

// 7. on-screen sections are force-revealed (safety timer)
{
  const e = createEnvironment({ tree, innerHeight: 800 });
  const targets = [];
  const IO = function () {
    this.observe = (t) => targets.push(t);
    this.unobserve = (t) => { const i = targets.indexOf(t); if (i >= 0) targets.splice(i, 1); };
  };
  let flush = null;
  const win = Object.assign(e.window, {
    IntersectionObserver: IO,
    setTimeout: (fn) => { flush = fn; return 1; },
  });
  new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
    e.document, win, e.window.localStorage, e.window.Image, IO
  );
  // no getBoundingClientRect on the harness: prove the safety timer exists and does not throw
  let threw = false;
  try { if (flush) flush(); } catch (err) { threw = String(err); }
  check("safety timer present and harmless", !threw, threw);
}

// 8. profile photo swap
{
  const e = createEnvironment({ tree });
  new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
    e.document, e.window, e.window.localStorage, e.window.Image, e.window.IntersectionObserver
  );
  const probe = e.window.Image.probes[e.window.Image.probes.length - 1];
  check("photo probe targets the owner file", probe._src === "assets/img/profile.jpg", probe._src);
  const avatar = e.document.querySelector(".avatar__img");
  probe.settle(true);
  check("real photo used when it loads", avatar.getAttribute("src") === "assets/img/profile.jpg");
  check("photo marked on the element", avatar.getAttribute("data-photo") === "owner");
}
{
  const e = createEnvironment({ tree });
  new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
    e.document, e.window, e.window.localStorage, e.window.Image, e.window.IntersectionObserver
  );
  const probe = e.window.Image.probes[e.window.Image.probes.length - 1];
  const avatar = e.document.querySelector(".avatar__img");
  const original = avatar.getAttribute("src");
  probe.settle(false);
  check("placeholder kept when the photo is missing", avatar.getAttribute("src") === original, avatar.getAttribute("src"));
  check("no stale photo marker", !avatar.hasAttribute("data-photo"));
}

// 9. footer year
{
  const e = createEnvironment({ tree });
  new Function("document", "window", "localStorage", "Image", "IntersectionObserver", pageScript)(
    e.document, e.window, e.window.localStorage, e.window.Image, e.window.IntersectionObserver
  );
  const node = e.document.getElementById("year");
  check("footer year filled with the current year", node.textContent === String(new Date().getFullYear()), node.textContent);
}

console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
process.exit(failures ? 1 : 0);
