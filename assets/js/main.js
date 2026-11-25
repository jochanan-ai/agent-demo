/* Personal one-page site: theme toggle, scroll reveal, avatar photo swap.
   No frameworks, no build step; the page also works with JavaScript disabled
   (dark theme, sections visible, placeholder avatar). */

(function () {
  "use strict";

  var root = document.documentElement;
  var STORAGE_KEY = "theme";
  var PHOTO_SRC = "assets/img/profile.jpg";

  function prefersReducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /* ---------- theme ---------- */

  function themeButton() {
    return document.getElementById("theme-toggle");
  }

  function currentTheme() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function describeButton(theme) {
    var button = themeButton();
    if (!button) {
      return;
    }
    var target = theme === "light" ? "dark" : "light";
    var label = button.querySelector(".theme-toggle__label");
    var text = theme === "light" ? "Light" : "Dark";
    button.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
    button.setAttribute("aria-label", "Switch to " + target + " theme");
    button.setAttribute("title", "Switch to " + target + " theme");
    if (label) {
      label.textContent = text;
    }
  }

  function storeTheme(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (err) {
      /* private mode or file:// restriction: the theme still applies for this page view */
    }
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    describeButton(theme);
    storeTheme(theme);
  }

  function initTheme() {
    describeButton(currentTheme());
    var button = themeButton();
    if (button) {
      button.addEventListener("click", function () {
        applyTheme(currentTheme() === "light" ? "dark" : "light");
      });
    }
    // Follow the OS only while the visitor has not chosen a theme themselves.
    if (window.matchMedia) {
      var query = window.matchMedia("(prefers-color-scheme: light)");
      var onChange = function (event) {
        var stored = null;
        try {
          stored = localStorage.getItem(STORAGE_KEY);
        } catch (err) {
          stored = null;
        }
        if (stored !== "light" && stored !== "dark") {
          root.setAttribute("data-theme", event.matches ? "light" : "dark");
          describeButton(currentTheme());
        }
      };
      if (typeof query.addEventListener === "function") {
        query.addEventListener("change", onChange);
      } else if (typeof query.addListener === "function") {
        query.addListener(onChange);
      }
    }
  }

  /* ---------- scroll reveal ---------- */

  function revealAll(sections) {
    for (var i = 0; i < sections.length; i += 1) {
      sections[i].classList.add("is-visible");
    }
  }

  function initReveal() {
    var sections = document.querySelectorAll("[data-reveal]");
    if (!sections.length) {
      return;
    }
    if (prefersReducedMotion() || typeof window.IntersectionObserver !== "function") {
      revealAll(sections);
      return;
    }
    var observer = new window.IntersectionObserver(
      function (entries, self) {
        for (var i = 0; i < entries.length; i += 1) {
          if (entries[i].isIntersecting) {
            entries[i].target.classList.add("is-visible");
            self.unobserve(entries[i].target);
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.08 }
    );
    for (var i = 0; i < sections.length; i += 1) {
      observer.observe(sections[i]);
    }
    // Sections already on screen when the page loads must never stay hidden.
    window.setTimeout(function () {
      for (var n = 0; n < sections.length; n += 1) {
        if (sections[n].getBoundingClientRect().top < window.innerHeight) {
          sections[n].classList.add("is-visible");
          observer.unobserve(sections[n]);
        }
      }
    }, 200);
  }

  /* ---------- profile photo ---------- */

  // The owner's photo is used as soon as assets/img/profile.jpg exists; until then the
  // self-contained SVG avatar stays in place, so a missing file never shows a broken image.
  function initAvatar() {
    var image = document.querySelector(".avatar__img");
    if (!image) {
      return;
    }
    var fallback = image.getAttribute("src");
    var probe = new Image();
    probe.onload = function () {
      image.src = PHOTO_SRC;
      image.dataset.photo = "owner";
    };
    probe.onerror = function () {
      image.src = fallback;
      image.removeAttribute("data-photo");
    };
    probe.src = PHOTO_SRC;
  }

  /* ---------- footer ---------- */

  function initYear() {
    var node = document.getElementById("year");
    if (node) {
      node.textContent = String(new Date().getFullYear());
    }
  }

  function init() {
    initTheme();
    initReveal();
    initAvatar();
    initYear();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
