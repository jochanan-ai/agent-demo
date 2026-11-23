/**
 * Minimal DOM for running the page's own assets/js/main.js under plain node.
 *
 * The element tree is not invented here: it is parsed from index.html by Python (html.parser) and
 * handed in as JSON, so main.js runs against the real markup of the real page. Only the browser
 * APIs main.js touches are implemented — nothing of the page logic is stubbed.
 */

class Element {
  constructor(tag, attrs = {}, children = []) {
    this.tagName = tag.toUpperCase();
    this.attributes = { ...attrs };
    this.childNodes = children;
    this.parentNode = null;
    this.listeners = new Map();
    for (const child of children) {
      child.parentNode = this;
    }
  }

  get className() {
    return this.attributes.class || "";
  }

  get id() {
    return this.attributes.id || "";
  }

  get classList() {
    const self = this;
    const read = () => (self.attributes.class || "").split(/\s+/).filter(Boolean);
    const write = (list) => {
      self.attributes.class = [...new Set(list)].join(" ");
    };
    return {
      add: (name) => write([...read(), name]),
      remove: (name) => write(read().filter((item) => item !== name)),
      contains: (name) => read().includes(name),
    };
  }

  get dataset() {
    const self = this;
    const toAttr = (key) => key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
    return new Proxy(
      {},
      {
        get: (_t, key) => self.attributes[`data-${toAttr(String(key))}`],
        set: (_t, key, value) => {
          self.attributes[`data-${toAttr(String(key))}`] = String(value);
          return true;
        },
        deleteProperty: (_t, key) => {
          delete self.attributes[`data-${toAttr(String(key))}`];
          return true;
        },
        has: (_t, key) => `data-${toAttr(String(key))}` in self.attributes,
      }
    );
  }

  getAttribute(name) {
    return name in this.attributes ? this.attributes[name] : null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  hasAttribute(name) {
    return name in this.attributes;
  }

  matches(selector) {
    const parts = selector.match(/(#[\w-]+|\.[\w-]+|\[[\w-]+\])/g) || [];
    return parts.every((part) => {
      if (part.startsWith("#")) return this.id === part.slice(1);
      if (part.startsWith(".")) return this.classList.contains(part.slice(1));
      return this.hasAttribute(part.slice(1, -1));
    });
  }

  walk(visit) {
    for (const child of this.childNodes) {
      if (child.tagName) {
        visit(child);
        child.walk(visit);
      }
    }
  }

  querySelectorAll(selector) {
    const found = [];
    this.walk((node) => {
      if (node.matches(selector)) found.push(node);
    });
    return found;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }

  dispatchEvent(event) {
    for (const handler of this.listeners.get(event.type) || []) {
      handler(event);
    }
    return true;
  }
}

class Storage {
  constructor(failing = false) {
    this.map = new Map();
    this.failing = failing;
  }

  getItem(key) {
    if (this.failing) throw new Error("SecurityError: storage is disabled");
    return this.map.has(key) ? this.map.get(key) : null;
  }

  setItem(key, value) {
    if (this.failing) throw new Error("SecurityError: storage is disabled");
    this.map.set(key, String(value));
  }
}

class MediaQueryList {
  constructor(matches) {
    this.matches = matches;
    this.listeners = [];
  }

  addEventListener(type, handler) {
    if (type === "change") this.listeners.push(handler);
  }

  addListener(handler) {
    this.listeners.push(handler);
  }

  emit(matches) {
    this.matches = matches;
    for (const handler of this.listeners) handler({ matches });
  }
}

class IntersectionObserver {
  constructor(callback) {
    this.callback = callback;
    this.targets = [];
  }

  observe(target) {
    this.targets.push(target);
  }

  unobserve(target) {
    this.targets = this.targets.filter((item) => item !== target);
  }

  /** test hook: report every observed target as visible */
  triggerVisible() {
    const entries = this.targets.map((target) => ({ isIntersecting: true, target }));
    this.callback(entries, this);
  }
}

class Image {
  constructor() {
    this._src = "";
    this.onload = null;
    this.onerror = null;
  }

  set src(value) {
    this._src = value;
    Image.probes.push(this);
  }

  get src() {
    return this._src;
  }

  /** test hook */
  settle(ok) {
    const handler = ok ? this.onload : this.onerror;
    if (handler) handler({ type: ok ? "load" : "error" });
  }
}
Image.probes = [];

export function createEnvironment({ tree, prefersDark = false, reducedMotion = false, storageFailing = false, innerHeight = 800 }) {
  const html = new Element("html", tree.attributes, tree.children);
  const timers = [];

  const window = {
    innerHeight,
    matchMedia: (query) => {
      const reduce = /prefers-reduced-motion/.test(query);
      const dark = /prefers-color-scheme:\s*dark/.test(query);
      const light = /prefers-color-scheme:\s*light/.test(query);
      const value = reduce ? reducedMotion : light ? !prefersDark : prefersDark;
      return new MediaQueryList(value);
    },
    setTimeout: (fn, delay) => {
      timers.push({ fn, delay });
      return timers.length;
    },
    IntersectionObserver,
    Image,
    localStorage: new Storage(storageFailing),
  };

  const document = new Element("html", tree.attributes, tree.children);
  document.documentElement = html;
  document.readyState = "complete";
  document.defaultView = window;
  document.getElementById = (id) => html.querySelector(`#${id}`);

  return { window, document, html, timers, flushTimers: () => timers.splice(0).forEach((t) => t.fn()) };
}
