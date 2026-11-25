/**
 * Minimal DOM for running the page's own assets/js/main.js under plain node.
 *
 * The element tree is not invented here: it is parsed from index.html by Python (html.parser) and
 * handed in as JSON, so main.js runs against the real markup of the real page. Only the browser
 * APIs main.js touches are implemented — nothing of the page logic is stubbed.
 */

class TextNode {
  constructor(text) {
    this.text = text;
    this.parentNode = null;
  }

  get textContent() {
    return this.text;
  }

  set textContent(value) {
    this.text = String(value);
  }
}

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

  get textContent() {
    return this.childNodes.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this.childNodes = [new TextNode(String(value))];
    this.childNodes[0].parentNode = this;
  }

  // main.js reads and writes image.src directly, so the property mirrors the attribute.
  get src() {
    return this.getAttribute("src") || "";
  }

  set src(value) {
    this.setAttribute("src", value);
  }

  getBoundingClientRect() {
    // no layout in the harness: the page only reads `top`, inherited from <html> (see createEnvironment)
    return this.__rect ?? this.parentNode?.getBoundingClientRect?.() ?? { top: 0 };
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

class ImageStub {
  constructor(probes) {
    this._src = "";
    this.onload = null;
    this.onerror = null;
    this._probes = probes;
  }

  set src(value) {
    this._src = value;
    this._probes.push(this);
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

/** JSON node from index.html (tests/test_page_js.py) -> Element / TextNode instances. */
function hydrate(node) {
  if ("text" in node) {
    return new TextNode(node.text);
  }
  return new Element(node.tag, node.attributes ?? {}, (node.children ?? []).map(hydrate));
}

export function createEnvironment({
  tree,
  prefersDark = false,
  reducedMotion = false,
  storageFailing = false,
  innerHeight = 800,
  onScreen = true,
}) {
  const documentElement = hydrate(tree);
  // the harness has no layout: every element reports its position through <html>
  documentElement.__rect = onScreen ? { top: 0 } : { top: Number.MAX_SAFE_INTEGER };
  const timers = [];
  const probes = [];
  const mediaQueries = [];

  const window = {
    innerHeight,
    matchMedia: (query) => {
      const reduce = /prefers-reduced-motion/.test(query);
      const dark = /prefers-color-scheme:\s*dark/.test(query);
      const light = /prefers-color-scheme:\s*light/.test(query);
      const value = reduce ? reducedMotion : light ? !prefersDark : prefersDark;
      const list = new MediaQueryList(value);
      list.query = query;
      mediaQueries.push(list);
      return list;
    },
    setTimeout: (fn, delay) => {
      timers.push({ fn, delay });
      return timers.length;
    },
    IntersectionObserver,
    localStorage: new Storage(storageFailing),
  };
  class EnvironmentImage extends ImageStub {
    constructor() {
      super(probes);
    }
  }
  window.Image = EnvironmentImage;

  const document = new Element("document", {}, [documentElement]);
  document.documentElement = documentElement;
  document.readyState = "complete";
  document.defaultView = window;
  document.getElementById = (id) => document.querySelector(`#${id}`);

  return {
    window,
    document,
    documentElement,
    html: documentElement,
    probes,
    timers,
    mediaQueries,
    flushTimers: () => timers.splice(0).forEach((t) => t.fn()),
  };
}
