/**
 * Headless runtime QA for generated web builds.
 *
 * Loads each HTML page in JSDOM, inlines its local <script src> files, executes
 * them (so DOMContentLoaded handlers run), and reports:
 *   - uncaught JS errors / exceptions thrown during load
 *   - pages that render almost nothing (likely JS-rendered content that failed)
 *
 * Usage:  node check.js <srcDir> page1.html page2.html ...
 * Output: a single JSON object on stdout:
 *   { "pages": [ { "page", "ok", "errors":[...], "elementCount", "textLength" } ] }
 *
 * This is a STATIC-DOM execution check (no network, fully offline). It catches the
 * common "querySelector returned null -> TypeError -> nothing renders" class of bug
 * that static structural checks miss.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const srcDir = process.argv[2];
const pages = process.argv.slice(3);

function inlineScripts(html, baseDir) {
  // Replace <script src="local.js"></script> with the file's contents inline so
  // JSDOM executes them synchronously (avoids the network resource loader).
  return html.replace(
    /<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>\s*<\/script>/gi,
    (m, src) => {
      if (/^https?:|^\/\//i.test(src)) return ""; // drop remote scripts (offline)
      const rel = src.replace(/^\.?\//, "");
      const p = path.join(baseDir, rel);
      try {
        if (fs.existsSync(p)) {
          const code = fs.readFileSync(p, "utf8");
          return "<script>\n" + code + "\n</script>";
        }
      } catch (e) {}
      return m;
    }
  );
}

async function checkPage(page) {
  const file = path.join(srcDir, page);
  const result = { page, ok: true, errors: [], elementCount: 0, textLength: 0 };
  if (!fs.existsSync(file)) {
    result.ok = false;
    result.errors.push("file not found");
    return result;
  }

  let html = fs.readFileSync(file, "utf8");
  html = inlineScripts(html, srcDir);

  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => {
    result.errors.push((e && (e.message || e.toString())) || "unknown jsdom error");
  });
  vc.on("error", (...args) => {
    result.errors.push("console.error: " + args.map(String).join(" "));
  });

  let dom;
  try {
    dom = new JSDOM(html, {
      runScripts: "dangerously",
      pretendToBeVisual: true,
      url: "http://localhost/" + page,
      virtualConsole: vc,
      beforeParse(window) {
        // Stub interactive dialogs so they don't throw / block.
        window.alert = () => {};
        window.confirm = () => true;
        window.prompt = () => null;
        // Some libs reference matchMedia.
        window.matchMedia = window.matchMedia || (() => ({
          matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
        }));
        // JSDOM does NOT implement several STANDARD browser APIs that modern, correct code
        // legitimately uses (scroll-reveal animations, responsive observers, rAF). Without
        // stubs the checker throws "X is not defined" and FALSELY fails good pages. These
        // are real-browser features, so we provide faithful no-op/standard stubs.
        if (typeof window.IntersectionObserver === "undefined") {
          // Fire the callback immediately as "intersecting" so scroll-reveal elements reveal
          // (mirrors what happens on screen) instead of staying hidden in the headless run.
          window.IntersectionObserver = class {
            constructor(cb) { this._cb = cb; }
            observe(el) {
              try { this._cb([{ isIntersecting: true, intersectionRatio: 1, target: el }], this); } catch (e) {}
            }
            unobserve() {} disconnect() {} takeRecords() { return []; }
          };
        }
        if (typeof window.ResizeObserver === "undefined") {
          window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
        }
        if (typeof window.requestAnimationFrame === "undefined") {
          window.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 0);
          window.cancelAnimationFrame = (id) => clearTimeout(id);
        }
        if (typeof window.requestIdleCallback === "undefined") {
          window.requestIdleCallback = (cb) => setTimeout(() => cb({ timeRemaining: () => 50, didTimeout: false }), 0);
          window.cancelIdleCallback = (id) => clearTimeout(id);
        }
        // scrollTo / scrollIntoView are unimplemented in JSDOM and throw "not implemented".
        window.scrollTo = window.scrollTo || (() => {});
        window.scroll = window.scroll || (() => {});
        if (window.Element && window.Element.prototype) {
          window.Element.prototype.scrollIntoView = window.Element.prototype.scrollIntoView || function () {};
        }
        // JSDOM doesn't implement form submission methods. requestSubmit() is the MODERN,
        // correct way to submit a form programmatically (it runs validation) — code using it
        // is right, so polyfill it to fire a cancelable submit event (what a browser does).
        // submit() bypasses the submit event in browsers, so stub it as a no-op.
        if (window.HTMLFormElement && window.HTMLFormElement.prototype) {
          const proto = window.HTMLFormElement.prototype;
          proto.requestSubmit = function () {
            this.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
          };
          proto.submit = function () {};
        }
      },
    });
  } catch (e) {
    result.ok = false;
    result.errors.push("JSDOM init: " + (e.message || String(e)));
    return result;
  }

  // Give async DOMContentLoaded / load handlers a tick to run.
  await new Promise((r) => setTimeout(r, 250));

  try {
    const doc = dom.window.document;
    const body = doc.body;
    result.elementCount = body ? body.querySelectorAll("*").length : 0;
    result.textLength = body ? body.textContent.replace(/\s+/g, " ").trim().length : 0;

    // ── Pinpoint DEAD SELECTORS: scan the page's JS for string-literal selectors
    // and test each against the actual DOM. Any that match nothing are the precise
    // cause of "null" crashes — report them so the fix is a one-liner.
    const deadGetById = new Set();
    const deadQuery = new Set();
    for (const re of [/getElementById\(\s*["'`]([^"'`]+)["'`]\s*\)/g]) {
      let m; while ((m = re.exec(html))) {
        const id = m[1];
        try { if (!doc.getElementById(id)) deadGetById.add(id); } catch (e) {}
      }
    }
    for (const re of [/querySelector(?:All)?\(\s*["'`]([^"'`]+)["'`]\s*\)/g]) {
      let m; while ((m = re.exec(html))) {
        const sel = m[1];
        try { if (!doc.querySelector(sel)) deadQuery.add(sel); } catch (e) { /* invalid selector */ }
      }
    }
    result.deadSelectors = {
      getElementById: [...deadGetById].slice(0, 15),
      querySelector: [...deadQuery].slice(0, 15),
    };
    // Inventory of what DOES exist, so the model can reconcile selectors.
    result.availableIds = [...doc.querySelectorAll("[id]")].map((e) => e.id).filter(Boolean).slice(0, 40);
    const cls = new Set();
    doc.querySelectorAll("[class]").forEach((e) => e.classList.forEach((c) => cls.add(c)));
    result.availableClasses = [...cls].slice(0, 40);

    // ── FUNCTIONAL TEST: actually exercise the interactions ─────────────────
    // Static "has a function" + "loads without error" is NOT enough — buttons must
    // DO something. We (1) verify inline onclick handlers reference real functions,
    // (2) click every button and submit every form, capturing thrown errors, and
    // (3) check that an "add"-type action actually mutates the DOM.
    const win = dom.window;
    const funcErrors = [];

    // (1) inline onclick="fnName(...)" must resolve to a global function
    doc.querySelectorAll("[onclick]").forEach((el) => {
      const code = el.getAttribute("onclick") || "";
      const m = code.match(/^\s*([A-Za-z_$][\w$]*)\s*\(/);
      if (m) {
        const fn = m[1];
        if (typeof win[fn] !== "function") {
          funcErrors.push(`onclick="${code.slice(0, 40)}" calls ${fn}() which is not defined globally (it is likely a local function inside DOMContentLoaded; inline onclick needs it on window — attach the listener in JS instead).`);
        }
      }
    });

    // Stub dialogs to return usable values so add/edit flows actually run.
    win.prompt = (msg = "") => {
      const m = String(msg).toLowerCase();
      if (m.includes("title")) return "Test Title";
      if (m.includes("body")) return "Test Body";
      if (m.includes("color")) return "#3498db";
      if (m.includes("index")) return "0";
      return "test";
    };
    win.confirm = () => true;
    win.alert = () => {};

    // (2)+(3) click buttons / [onclick] and watch for thrown errors + DOM change
    const clickErrCountBefore = result.errors.length;
    const clickables = [...doc.querySelectorAll("button, [onclick], a.btn, [role='button']")].slice(0, 20);
    let anyDomChange = false;
    for (const el of clickables) {
      const label = (el.id || el.textContent || el.getAttribute("onclick") || "button").trim().slice(0, 30);
      const before = doc.body.querySelectorAll("*").length;
      try {
        el.dispatchEvent(new win.MouseEvent("click", { bubbles: true, cancelable: true }));
      } catch (e) {
        funcErrors.push(`click "${label}" threw: ${e.message || e}`);
      }
      const after = doc.body.querySelectorAll("*").length;
      if (after !== before) anyDomChange = true;
    }
    // Errors thrown inside handlers surface via the virtual console -> result.errors
    const handlerErrs = result.errors.slice(clickErrCountBefore);
    for (const he of handlerErrs) funcErrors.push("on click: " + he);
    result.errors.length = clickErrCountBefore; // move them into funcErrors bucket

    // submit any forms
    doc.querySelectorAll("form").forEach((form) => {
      try {
        form.dispatchEvent(new win.Event("submit", { bubbles: true, cancelable: true }));
      } catch (e) {
        funcErrors.push(`form submit threw: ${e.message || e}`);
      }
    });

    result.functionalErrors = funcErrors;
    result.interactionDomChanged = anyDomChange;
    result.hadClickables = clickables.length > 0;
  } catch (e) {
    result.errors.push("post-load inspect: " + (e.message || String(e)));
  }

  // ok = no load errors AND no functional errors
  result.functionalErrors = result.functionalErrors || [];

  try { dom.window.close(); } catch (e) {}

  result.functionalErrors = result.functionalErrors || [];
  result.ok = result.errors.length === 0 && result.functionalErrors.length === 0;
  return result;
}

(async () => {
  const out = { pages: [] };
  for (const page of pages) {
    try {
      out.pages.push(await checkPage(page));
    } catch (e) {
      out.pages.push({ page, ok: false, errors: ["checker crash: " + (e.message || String(e))], elementCount: 0, textLength: 0 });
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
