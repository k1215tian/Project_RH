/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { Chatter } from "@mail/chatter/web_portal/chatter";
import { onWillUpdateProps, useState } from "@odoo/owl";

import { ExcalidrawPickerDialog } from "./excalidraw_dialogs";

// Session-level caches (design §3.1): the group check runs once per session
// (the user service caches hasGroup anyway) and the model-level write-ACL
// check runs once per distinct host model per session.
const excalidrawCaches = {
    groupCheckDone: false,
    groupCheckResult: false,
    modelWriteAccess: new Map(), // Map<modelName, Boolean>
};

async function isExcalidrawGroupUser() {
    if (!excalidrawCaches.groupCheckDone) {
        excalidrawCaches.groupCheckResult = await user.hasGroup(
            "excalidraw_for_odoo.group_excalidraw_user",
        );
        excalidrawCaches.groupCheckDone = true;
    }
    return excalidrawCaches.groupCheckResult;
}

/** Model-level write ACL signal (O1): cached per model; any RPC failure
 * degrades to `true` (visible button + friendly controller error on save) —
 * the spec-sanctioned degradation, the controller stays the source of truth
 * (FR-ACCESS-1). Record-rule denials are intentionally not detected here. */
async function modelWriteAccess(model) {
    if (!excalidrawCaches.modelWriteAccess.has(model)) {
        let access = true;
        try {
            access = await rpc("/web/dataset/call_kw", {
                model,
                method: "check_access_rights",
                args: ["write"],
                kwargs: { raise_exception: false },
            });
        } catch (error) {
            console.error(
                "excalidraw_for_odoo: write access check failed",
                error,
            );
            access = true;
        }
        excalidrawCaches.modelWriteAccess.set(model, access);
    }
    return excalidrawCaches.modelWriteAccess.get(model);
}

patch(Chatter.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");

        // Reactive visibility: default hidden so the button never flashes
        // while the async checks resolve (and never renders at all for
        // non-members or unsaved records — FR-ENTRY-1).
        this.excalidraw = useState({ visible: false });
        this.excalidrawButtonTitle = _t("Add or edit an Excalidraw drawing");

        this.resolveExcalidrawVisibility(this.props);
        onWillUpdateProps((nextProps) => {
            if (!this.props.threadId && nextProps.threadId) {
                // The record was just saved (threadId falsy → truthy) while
                // the chatter stayed open.
                this.resolveExcalidrawVisibility(nextProps);
            }
        });
    },

    async resolveExcalidrawVisibility(props) {
        if (!props.threadId) {
            // Unsaved record: hidden, zero RPCs (FR-ENTRY-1).
            this.excalidraw.visible = false;
            return;
        }
        if (!(await isExcalidrawGroupUser())) {
            this.excalidraw.visible = false;
            return;
        }
        this.excalidraw.visible = await modelWriteAccess(props.threadModel);
    },

    openExcalidraw() {
        this.dialog.add(ExcalidrawPickerDialog, {
            resModel: this.props.threadModel,
            resId: this.props.threadId,
            onSaved: async () => {
                await this.refreshAttachments();
            },
        });
    },

    /** Chatter refresh fallback chain (FR-SAVE-1), each step guarded — the
     * onlyoffice-proven chain for this build. */
    async refreshAttachments() {
        try {
            if (
                this.attachmentList &&
                typeof this.attachmentList.load === "function"
            ) {
                await this.attachmentList.load();
            } else if (typeof this.reloadAttachments === "function") {
                await this.reloadAttachments();
            } else if (this.props && typeof this.props.onSave === "function") {
                await this.props.onSave();
            }
        } catch (error) {
            console.error(
                "excalidraw_for_odoo: could not refresh attachments",
                error,
            );
        }
    },
});
