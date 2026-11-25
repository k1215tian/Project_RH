/** @odoo-module **/

/**
 * Loader for the vendored Excalidraw bundle.
 *
 * The library (@excalidraw/excalidraw 0.18.1 + React 18 runtime) is bundled
 * with esbuild into `static/lib/excalidraw/` as a self-contained ESM module.
 * Neither its JS nor its CSS is registered in the Odoo asset bundles:
 *
 * - the JS is loaded through a native dynamic import() so its own
 *   code-split chunks resolve relative to the module static URL;
 * - the CSS is injected as a <link> at runtime so it never goes through
 *   Odoo's libsass pipeline (modern CSS, e.g. color-mix, would break it).
 *
 * Fonts are fetched from `window.EXCALIDRAW_ASSET_PATH` (Excalidraw
 * runtime contract), which we point to the vendored fonts directory.
 */

const MODULE_BASE = "/excalidraw_for_odoo/static/lib/excalidraw";

let loadPromise = null;
let cssPromise = null;

export function ensureExcalidrawAssetPath() {
    let base = `${MODULE_BASE}/`;
    if (!base.endsWith("/")) {
        base += "/";
    }
    window.EXCALIDRAW_ASSET_PATH = base;
    return base;
}

/** Inject the vendored stylesheet once; resolve when it is applied. */
export function loadExcalidrawCss() {
    if (!cssPromise) {
        cssPromise = new Promise((resolve, reject) => {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = `${MODULE_BASE}/excalidraw.css`;
            link.onload = () => resolve();
            link.onerror = () => {
                cssPromise = null; // allow retry on failure
                reject(new Error(`Failed to load ${link.href}`));
            };
            document.head.append(link);
        });
    }
    return cssPromise;
}

export function loadExcalidraw() {
    if (!loadPromise) {
        ensureExcalidrawAssetPath();
        loadExcalidrawCss().catch((error) => {
            // Best-effort: the editor still renders unstyled-but-usable; the
            // JS bundle itself is the critical piece below.
            console.error("excalidraw_for_odoo: css load failed", error);
        });
        // Computed specifier: keeps the dynamic import opaque to any static
        // bundler/transpiler pass, so it stays a native runtime import().
        const specifier = [
            "/excalidraw_for_odoo",
            "/static/lib/excalidraw/excalidraw.vendor.js",
        ].join("");
        loadPromise = import(/* webpackIgnore: true */ specifier).catch(
            (error) => {
                // Allow a later retry instead of caching the failure forever.
                loadPromise = null;
                throw error;
            },
        );
    }
    return loadPromise;
}
