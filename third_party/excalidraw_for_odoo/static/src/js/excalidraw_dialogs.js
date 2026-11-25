/** @odoo-module **/

import {
    Component,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

import { loadExcalidraw } from "./excalidraw_loader";

// Autosave cadence (design §3.2.2 / O2): 45 s inactivity debounce, plus a
// 60 s max-latency guard so continuous drawing sessions still persist at
// least every 60 s (a pure debounce would never fire while the user keeps
// drawing).
const AUTOSAVE_DEBOUNCE_MS = 45000;
const AUTOSAVE_MAX_LATENCY_MS = 60000;

/** Map an Odoo user lang to the closest Excalidraw locale code. */
function excalidrawLang(odooLang) {
    const fallbacks = {
        es: "es-ES",
        pt: "pt-BR",
        en: "en",
        fr: "fr-FR",
        de: "de-DE",
        it: "it-IT",
        zh: "zh-CN",
    };
    const normalized = (odooLang || "en").replace("_", "-");
    const [base] = normalized.split("-");
    return fallbacks[base] || normalized;
}

/** Detect the Odoo webclient color scheme ("light" | "dark").
 * Odoo 19 exposes the --o-webclient-color-scheme custom property on the
 * webclient root (body.o_web_client), with values "bright" | "dark". */
function webclientTheme() {
    const webclient = document.querySelector("body.o_web_client, .o_webclient");
    if (webclient) {
        const scheme = getComputedStyle(webclient)
            .getPropertyValue("--o-webclient-color-scheme")
            .trim();
        if (scheme) {
            return scheme === "dark" ? "dark" : "light";
        }
    }
    if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
        return "dark";
    }
    return "light";
}

/** Convert a PNG blob to a base64 string (without the data: prefix) via
 * FileReader.readAsDataURL — handles multi-MB blobs without string-quota
 * pitfalls (design §3.2.2). */
function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () =>
            reject(reader.error || new Error("FileReader failed"));
        reader.readAsDataURL(blob);
    });
}

/** Auto-name a new drawing: "Drawing YYYY-MM-DD HH:mm", collision-suffixed
 * " (2)", " (3)", ... when the record already holds a drawing named this
 * minute (FR-NAME-1 + design decision #8). The prefix "Drawing " and the
 * format are pinned by the spec and stay untranslated.
 *
 * O5 fallback: the design's `localize(DateTime.now())` helper from
 * "@web/core/luxon_utils" does not exist in Odoo 19 — luxon is a bundle
 * global (same as core's core/l10n/dates.js), so the local clock is used
 * directly. */
export function generateDrawingName(existingNames) {
    const base = `Drawing ${luxon.DateTime.now().toFormat("yyyy-MM-dd HH:mm")}`;
    const taken = new Set(
        (existingNames || []).map((name) => (name || "").trim().toLowerCase()),
    );
    if (!taken.has(base.toLowerCase())) {
        return base;
    }
    let counter = 2;
    let candidate = `${base} (${counter})`;
    while (taken.has(candidate.toLowerCase())) {
        counter += 1;
        candidate = `${base} (${counter})`;
    }
    return candidate;
}

// ─────────────────────────────────────────────────────────────────
//  Picker dialog — lists the record's .excalidraw attachments and
//  opens the editor on an existing scene or on a fresh one.
// ─────────────────────────────────────────────────────────────────
export class ExcalidrawPickerDialog extends Component {
    static components = { Dialog };
    static template = "excalidraw_for_odoo.PickerDialog";
    static props = {
            // Injected by the dialog service on every dialog.add() call —
            // must be declared or Owl 2 strict validation rejects it.
            close: { type: Function, optional: true },
        resModel: String,
        resId: { type: [Number, String] },
        onSaved: { type: Function, optional: true },
    };

    setup() {
        this.data = this.env.dialogData;
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.dialogTitle = _t("Excalidraw drawings");
        this.labels = {
            loading: _t("Loading drawings…"),
            empty: _t("No drawings yet"),
            open: _t("Open this drawing"),
            new: _t("New drawing"),
            close: _t("Close"),
        };

        this.state = useState({
            loading: true,
            attachments: [], // [{ id, name, write_date }]
            openingId: null, // attachment id whose row shows a spinner
        });
        this.loadAttachments();
    }

    /** Basenames (name without the .excalidraw suffix) of the listed scenes. */
    get existingNames() {
        return this.state.attachments.map((att) =>
            att.name.replace(/\.excalidraw$/, ""),
        );
    }

    /** Localized write_date (session timezone via deserializeDateTime). */
    formatStamp(att) {
        try {
            return formatDateTime(deserializeDateTime(att.write_date));
        } catch {
            return att.write_date || "";
        }
    }

    async loadAttachments() {
        this.state.loading = true;
        try {
            // IR-ROUTE-3 (CR-1 Option A): scene rows carry the internal
            // res_field marker and are invisible to plain search_read —
            // the gated controller route lists them (newest first,
            // PNG twins excluded, half-pair tolerant).
            const result = await rpc("/excalidraw/chatter/list", {
                res_model: this.props.resModel,
                res_id: this.props.resId,
            });
            if (result.error) {
                // Error envelope: treat as an empty list — the picker
                // stays functional.
                console.error(
                    "excalidraw_for_odoo: could not list drawings",
                    result.error,
                );
                this.state.attachments = [];
            } else {
                this.state.attachments = result.drawings || [];
            }
        } catch (error) {
            // Route failure: treat as an empty list — the picker stays
            // functional.
            console.error(
                "excalidraw_for_odoo: could not list drawings",
                error,
            );
            this.state.attachments = [];
        } finally {
            this.state.loading = false;
        }
    }

    onNew() {
        this.data.close();
        this.dialog.add(ExcalidrawEditorDialog, {
            resModel: this.props.resModel,
            resId: this.props.resId,
            name: generateDrawingName(this.existingNames),
            // `initialScene` deliberately omitted (= absent prop), NOT
            // `null`: OWL's validator rejects an explicit null for a
            // `type: [String, Boolean]` union (verified against this
            // build's owl.js). An absent prop yields a fresh scene via
            // buildInitialData(undefined) — same BR-SCENE-2 semantics.
            onSaved: this.props.onSaved,
        });
    }

    async onOpenExisting(att) {
        if (this.state.openingId !== null) {
            return;
        }
        this.state.openingId = att.id;
        let scene = null;
        try {
            const result = await rpc("/excalidraw/chatter/scene", {
                attachment_id: att.id,
            });
            if (result.error) {
                this.notification.add(result.error, {
                    type: "warning",
                    sticky: false,
                });
                this.state.openingId = null;
                return;
            }
            scene = result.scene;
        } catch (error) {
            console.error("excalidraw_for_odoo: could not load drawing", error);
            this.notification.add(_t("Could not load the drawing"), {
                type: "warning",
                sticky: false,
            });
            this.state.openingId = null;
            return;
        }
        this.data.close();
        this.dialog.add(ExcalidrawEditorDialog, {
            resModel: this.props.resModel,
            resId: this.props.resId,
            name: att.name.replace(/\.excalidraw$/, ""),
            initialScene: scene,
            onSaved: this.props.onSaved,
        });
    }
}

// ─────────────────────────────────────────────────────────────────
//  Editor dialog — fullscreen web Dialog hosting the vendored React
//  Excalidraw bundle (React lifecycle ported verbatim from the legacy
//  standalone field widget — design §3.2.2 / D10).
// ─────────────────────────────────────────────────────────────────
export class ExcalidrawEditorDialog extends Component {
    static components = { Dialog };
    static template = "excalidraw_for_odoo.EditorDialog";
    static props = {
            // Injected by the dialog service on every dialog.add() call —
            // must be declared or Owl 2 strict validation rejects it.
            close: { type: Function, optional: true },
        resModel: String,
        resId: { type: [Number, String] },
        name: String,
        initialScene: { type: [String, Boolean], optional: true },
        onSaved: { type: Function, optional: true },
    };

    setup() {
        this.data = this.env.dialogData;
        this.notification = useService("notification");
        this.containerRef = useRef("excalidraw_container");

        this.state = useState({ loading: false, error: "" });
        this.lib = null;
        this.reactRoot = null;
        this.excalidrawAPI = null;
        this.mountToken = 0;

        // Editor theme: null = follow the webclient color scheme, otherwise
        // a manual "light" | "dark" choice kept until the dialog closes.
        this.manualTheme = null;
        this.reactProps = null;
        this._schemeObserver = null;

        this._autosaveTimer = null;
        this._latestElements = null;
        this._latestAppState = null;
        // Last persisted serialization (the raw initial scene *is* what is
        // stored) — the hash-skip guard short-circuits saves when nothing
        // changed since the last successful flush (FR-SAVE-1 / A5).
        this._lastSavedSerialized = this.props.initialScene || "";
        this._lastFlushAt = Date.now();
        this._saving = false;
        this._saveQueued = false;

        // Mount the React editor once ([] deps). OWL re-renders never touch
        // the React root: the t-ref div is a stable node in an otherwise
        // static subtree (R2). Cleanup unmounts on dialog destruction.
        useEffect(
            () => {
                const el = this.containerRef.el;
                if (el) {
                    this.mountEditor(el);
                }
                return () => this.destroyEditor();
            },
            () => [],
        );

        // Close-flush (FR-SAVE-1): every close path (ESC, back-arrow, dialog
        // service) unmounts the component; saveNow() is fire-and-forget —
        // the standalone rpc() and the notification service outlive the OWL
        // lifecycle — then the React editor is torn down.
        onWillUnmount(() => {
            this.saveNow();
            this.destroyEditor();
        });

        // Follow webclient dark-mode switches while no manual choice was made.
        this._schemeObserver = new MutationObserver(() => {
            if (this.manualTheme === null) {
                this.applyEditorTheme();
            }
        });
        this._schemeObserver.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class", "style", "data-color-mode"],
        });
        this._schemeObserver.observe(document.body, {
            attributes: true,
            attributeFilter: ["class", "style"],
        });
    }

    get dialogTitle() {
        return this.props.name || _t("Excalidraw drawing");
    }

    get loadingLabel() {
        return _t("Loading the Excalidraw editor…");
    }

    get effectiveTheme() {
        return this.manualTheme ?? webclientTheme();
    }

    get themeTooltip() {
        return this.effectiveTheme === "dark"
            ? _t("Switch to light theme")
            : _t("Switch to dark theme");
    }

    toggleTheme() {
        this.manualTheme = this.effectiveTheme === "dark" ? "light" : "dark";
        this.applyEditorTheme();
    }

    /** Re-render the React root with the current theme, preserving the scene
     * (initialData only applies on mount, so React reconciliation keeps the
     * internal editor state intact). */
    applyEditorTheme() {
        if (this.reactProps && this.reactRoot && this.lib) {
            this.reactProps.theme = this.effectiveTheme;
            this.reactRoot.render(
                this.lib.React.createElement(
                    this.lib.Excalidraw,
                    this.reactProps,
                ),
            );
        }
    }

    // ------------------------------------------------------------------
    // Editor lifecycle
    // ------------------------------------------------------------------

    async mountEditor(el) {
        const token = ++this.mountToken;
        this.state.loading = true;
        this.state.error = "";
        try {
            const lib = await loadExcalidraw();
            if (token !== this.mountToken || !this.containerRef.el) {
                return; // stale mount
            }
            this.lib = lib;
            this.reactRoot = lib.ReactDOMClient.createRoot(el);
            this.reactProps = {
                initialData: this.buildInitialData(this.props.initialScene),
                onChange: (elements, appState) =>
                    this.scheduleAutosave(elements, appState),
                excalidrawAPI: (api) => {
                    if (token === this.mountToken) {
                        this.excalidrawAPI = api;
                    }
                },
                lang: excalidrawLang(user.lang),
                theme: this.effectiveTheme,
                name: this.props.name || "drawing",
                gridMode: null,
            };
            this.reactRoot.render(
                lib.React.createElement(lib.Excalidraw, this.reactProps),
            );
        } catch (error) {
            if (token === this.mountToken) {
                this.state.error = `${_t("Could not load the Excalidraw editor")}: ${error?.message || error}`;
            }
        } finally {
            if (token === this.mountToken) {
                this.state.loading = false;
            }
        }
    }

    destroyEditor() {
        // Flush pending autosave so the last strokes are never lost.
        if (this._autosaveTimer) {
            clearTimeout(this._autosaveTimer);
            this._autosaveTimer = null;
            this.saveNow();
        }
        this.mountToken++;
        // Note: unlike the legacy field widget (whose flush was synchronous),
        // _latestElements/_latestAppState are deliberately NOT nulled here —
        // saveNow() is async and a queued re-check after an in-flight save
        // still needs them (see saveNow).
        this.reactProps = null;
        if (this._schemeObserver) {
            this._schemeObserver.disconnect();
            this._schemeObserver = null;
        }
        if (this.reactRoot) {
            try {
                this.reactRoot.unmount();
            } catch {
                // React root may already be gone with its container.
            }
            this.reactRoot = null;
        }
        this.excalidrawAPI = null;
    }

    // ------------------------------------------------------------------
    // Scene serialization / persistence
    // ------------------------------------------------------------------

    buildInitialData(raw) {
        if (raw) {
            try {
                const parsed = JSON.parse(raw);
                if (Array.isArray(parsed.elements)) {
                    return {
                        elements: parsed.elements,
                        appState: {
                            viewBackgroundColor:
                                parsed.appState?.viewBackgroundColor ||
                                "#ffffff",
                        },
                        files: parsed.files || {},
                    };
                }
            } catch {
                // Fall back to a fresh scene when stored data is invalid
                // (BR-SCENE-2 end-to-end).
            }
        }
        return {
            appState: { viewBackgroundColor: "#ffffff" },
            elements: [],
            files: {},
        };
    }

    serializeScene(elements, appState) {
        const files = {};
        for (const [fileId, file] of Object.entries(
            this.excalidrawAPI?.getFiles() || {},
        )) {
            files[fileId] = {
                dataURL: file.dataURL,
                mimeType: file.mimeType,
                created: file.created,
            };
        }
        return JSON.stringify({
            type: "excalidraw",
            version: 2,
            source: "excalidraw_for_odoo",
            elements,
            appState: {
                viewBackgroundColor: appState?.viewBackgroundColor || "#ffffff",
            },
            files,
        });
    }

    /** Cache the latest scene and (re)start the 45 s debounce; fire
     * saveNow() immediately when the last flush is older than 60 s
     * (max-latency guard, O2). */
    scheduleAutosave(elements, appState) {
        this._latestElements = elements;
        this._latestAppState = appState;
        clearTimeout(this._autosaveTimer);
        this._autosaveTimer = setTimeout(() => {
            this._autosaveTimer = null;
            this.saveNow();
        }, AUTOSAVE_DEBOUNCE_MS);
        if (Date.now() - this._lastFlushAt > AUTOSAVE_MAX_LATENCY_MS) {
            this.saveNow();
        }
    }

    /** Persist the latest scene + PNG twin via the chatter controller.
     * Idempotent and fire-and-forget safe (hash-skip + re-entrancy guard):
     * repeated/overlapping calls never issue duplicate or out-of-order RPCs. */
    async saveNow() {
        if (this._autosaveTimer) {
            clearTimeout(this._autosaveTimer);
            this._autosaveTimer = null;
        }
        if (this._saving) {
            // A save is in flight: re-check once it completes, so changes
            // made during the flight still persist in order.
            this._saveQueued = true;
            return;
        }
        const elements = this._latestElements;
        const appState = this._latestAppState;
        if (!elements) {
            return; // nothing changed since mount — no RPC (A5 / M4)
        }
        const serialized = this.serializeScene(elements, appState);
        if (serialized === this._lastSavedSerialized) {
            return; // hash-skip: untouched scene ⇒ no PNG export, no RPC
        }
        this._saving = true;
        this._lastFlushAt = Date.now();
        try {
            let png = null;
            if (elements.length > 0) {
                // Element-less scenes never export a PNG (BR-EMPTY-1).
                try {
                    const blob = await this.lib.exportToBlob({
                        elements,
                        appState,
                        files: this.excalidrawAPI?.getFiles() || {},
                        mimeType: "image/png",
                        exportScale: 2, // O3 / DR-PNG-1
                    });
                    png = await blobToBase64(blob);
                } catch (error) {
                    // PNG export is best-effort: never block the scene save
                    // (the twin is regenerated on the next changed save).
                    console.error(
                        "excalidraw_for_odoo: PNG export failed",
                        error,
                    );
                }
            }
            const result = await rpc("/excalidraw/chatter/save", {
                res_model: this.props.resModel,
                res_id: this.props.resId,
                name: this.props.name,
                scene: serialized,
                png,
            });
            if (result.error) {
                this.notification.add(result.error, {
                    type: "warning",
                    sticky: false,
                });
                // _lastSavedSerialized stays untouched so the next
                // tick/close retries automatically.
            } else {
                this._lastSavedSerialized = serialized;
                if (this.props.onSaved) {
                    await this.props.onSaved(); // chatter refresh chain
                }
            }
        } finally {
            this._saving = false;
            if (this._saveQueued) {
                this._saveQueued = false;
                this.saveNow();
            }
        }
    }

    // ------------------------------------------------------------------
    // Keyboard containment (design §8.1)
    // ------------------------------------------------------------------

    /** Targeted, Escape-exempt stopPropagation on the editor wrapper: listed
     * keys (canvas shortcuts) never reach document-level Odoo consumers,
     * while Escape keeps flowing to the dialog service (FR-EDITOR-2) and Tab
     * keeps any focus trap intact. Never preventDefault — Excalidraw keeps
     * its native behavior. */
    containKeydown(ev) {
        if (ev.key === "Escape") {
            return; // ESC must reach the dialog service (FR-EDITOR-2)
        }
        const k = ev.key;
        const contained =
            [
                "ArrowUp",
                "ArrowDown",
                "ArrowLeft",
                "ArrowRight",
                " ",
                "Delete",
                "Backspace",
            ].includes(k) ||
            ((ev.ctrlKey || ev.metaKey) &&
                ["z", "Z", "y", "Y", "k", "K"].includes(k));
        if (contained) {
            ev.stopPropagation();
        }
    }
}
