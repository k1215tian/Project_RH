# Local dev environments do not ship the odoo package; the runtime imports
# are resolved inside the odoo:19 container. Same suppression pattern as the
# sibling `drawing` module manifest.
# pyright: reportMissingImports=false
"""JSON-RPC controller for the Excalidraw chatter tool (design §4).

Persistence model: an ``ir.attachment`` pair per drawing (editable scene JSON
``<name>.excalidraw`` + PNG render ``<name>.png``) upserted on the host record
by exact ``(res_model, res_id, res_field, name)``. The scene row carries the
internal ``excalidraw_scene`` marker (hidden from chatter); the PNG keeps
``res_field = False`` (visible).

Security model (FR-ACCESS-1): the controller is the source of truth and checks
group membership → generic chatter-capability of the model → record existence
→ write access, all before any validation side effect or attachment write.
Odoo 19 hard-denies non-system ORM access to ``res_field``-marker rows and
record rules cannot lift it (probe 2026-09-04, CR-1 Option A), so scene-row
attachment operations run via ``sudo()`` strictly AFTER those real-user
gates — the gates, not attachment record rules, are the security boundary
for scene rows (DR-ATT-1 as amended).
"""

import base64
import binascii
import json
import logging
import re

from odoo import _, fields, http
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

_UNSAFE_FILENAME_CHARS = re.compile(r"[\/\\:*?\"<>|]")
_MAX_NAME_LENGTH = 100

_GROUP_USER = "excalidraw_for_odoo.group_excalidraw_user"

# Internal marker of the scene half of the pair (DR-ATT-1 as amended by
# CR-1/S12): chatter attachment domains exclude res_field != False, so the
# machine artifact stays hidden; the PNG half stays res_field=False.
SCENE_RES_FIELD = "name"  # 17/18: a real field on every model — markers
# pointing at nonexistent fields crash ir_attachment._search
# (core _fields[res_field] KeyError) for non-system users.


class ExcalidrawChatterController(http.Controller):
    """Routes for saving and fetching chatter-hosted Excalidraw drawings."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_int(value):
        """Coerce a route param to an id, missing-records-style on failure."""
        try:
            return int(value)
        except (TypeError, ValueError) as ex:
            raise MissingError(
                _("The record does not exist or has been deleted.")
            ) from ex

    def _check_group(self):
        """Refuse non-group users (FR-ACCESS-1 step 1)."""
        if not request.env.user.has_group(_GROUP_USER):
            raise AccessError(
                _("You are not allowed to use the Excalidraw drawing tool.")
            )

    def _chatter_model(self, res_model):
        """Return the model's env, or raise a generic, non-enumerating error."""
        if not isinstance(res_model, str) or res_model not in request.env:
            raise ValueError(_("Model is not found or does not support Chatter."))
        model = request.env[res_model]
        if not hasattr(model, "message_post"):
            # Same fixed message as the unknown-model case: nothing
            # distinguishes "unknown" from "chatter-less" client-side.
            raise ValueError(_("Model is not found or does not support Chatter."))
        return model

    def _parse_scene(self, scene):
        """Validate the posted scene document (BR-SCENE-1) and return its text.

        Mirrors the invariant previously enforced by the legacy standalone
        editor: JSON dict containing an ``elements`` key (which may be an
        empty list).
        """
        if not isinstance(scene, str) or not scene.strip():
            raise ValueError(
                _(
                    "The scene is not a valid Excalidraw document: "
                    "it must be a JSON object with an 'elements' key."
                )
            )
        try:
            parsed = json.loads(scene)
        except (TypeError, ValueError) as ex:
            raise ValueError(
                _(
                    "The scene is not a valid Excalidraw document: "
                    "it must be a JSON object with an 'elements' key."
                )
            ) from ex
        if not isinstance(parsed, dict) or "elements" not in parsed:
            raise ValueError(
                _(
                    "The scene is not a valid Excalidraw document: "
                    "it must be a JSON object with an 'elements' key."
                )
            )
        return scene

    def _decode_png(self, png):
        """Decode the optional PNG payload; ``None`` when absent/empty."""
        if png is None or png == "":
            return None
        try:
            return base64.b64decode(png, validate=True)
        except (binascii.Error, ValueError) as ex:
            raise ValueError(_("Invalid PNG data.")) from ex

    def _sanitize_name(self, name):
        """Sanitize and truncate the drawing basename (FR-NAME-1, O4)."""
        name = _UNSAFE_FILENAME_CHARS.sub("_", (name or "").strip())
        name = name[:_MAX_NAME_LENGTH].rstrip(". ")
        if name:
            return name
        timestamp = fields.Datetime.context_timestamp(
            request.env.user, fields.Datetime.now()
        )
        return _("Drawing %s") % timestamp.strftime("%Y-%m-%d %H:%M:%S")

    def _upsert_attachment(
        self, name, mimetype, raw, res_model, res_id, res_field, sudo_ops
    ):
        """Upsert one attachment of the pair by exact field identity
        (FR-PAIR-1, DR-ATT-1): write in place when a row exists, create
        otherwise. No unique constraint is needed — this search is the
        mechanism. Scene rows (marker, ``sudo_ops=True``) are operated
        via sudo() — plain users cannot access marker rows (platform
        hard-deny; the route's real-user gates ran before this call).
        PNG rows keep res_field=False and use normal user operations."""
        env = (
            request.env["ir.attachment"].sudo()
            if sudo_ops
            else request.env["ir.attachment"]
        )
        attachment = env.search(
            [
                ("res_model", "=", res_model),
                ("res_id", "=", res_id),
                ("res_field", "=", res_field),
                ("name", "=", name),
            ],
            limit=1,
        )
        if attachment:
            attachment.write({"raw": raw})
            return attachment
        return env.create(
            {
                "name": name,
                "mimetype": mimetype,
                "raw": raw,
                "res_model": res_model,
                "res_id": res_id,
                "res_field": res_field,
                "public": False,
                "url": False,
            }
        )

    # ------------------------------------------------------------------
    # IR-ROUTE-1 — save (upsert the pair)
    # ------------------------------------------------------------------

    @http.route(
        "/excalidraw/chatter/save",
        auth="user",
        methods=["POST"],
        type="json",
    )
    def excalidraw_chatter_save(
        self, res_model=None, res_id=None, name="", scene=None, png=None
    ):
        """Persist one drawing as the attachment pair on the host record."""
        result = {"ok": False, "scene_id": None, "png_id": None}
        try:
            # 1. Group gate (cheapest, first).
            self._check_group()
            # 2. Generic chatter-capability model gate (anti-enumeration).
            model = self._chatter_model(res_model)
            # 3. Record gate: phantom ids must be rejected explicitly
            #    (``browse().ensure_one()`` alone would not).
            res_id_int = self._to_int(res_id)
            record = model.browse(res_id_int).exists()
            if not record:
                raise MissingError(_("The record does not exist or has been deleted."))
            # 4. Write gate: ACLs + record rules.
            record.check_access_rights("write")
            record.check_access_rule("write")
            # 5. Scene validation — nothing is written before this point.
            scene_text = self._parse_scene(scene)
            # 6. PNG validation (decodability only; frontend-only producer).
            png_bytes = self._decode_png(png)
            # 7. Name handling with server-side timestamp fallback.
            drawing_name = self._sanitize_name(name)
            # 8. Upsert the pair (FR-PAIR-1, DR-ATT-1): scene via sudo
            #    (marker row), PNG as the current user (visible row).
            scene_attachment = self._upsert_attachment(
                f"{drawing_name}.excalidraw",
                "application/json",
                scene_text.encode("utf-8"),
                res_model,
                res_id_int,
                SCENE_RES_FIELD,
                sudo_ops=True,
            )
            png_attachment = None
            if png_bytes is not None:
                png_attachment = self._upsert_attachment(
                    f"{drawing_name}.png",
                    "image/png",
                    png_bytes,
                    res_model,
                    res_id_int,
                    False,
                    sudo_ops=False,
                )
            # 9. Success.
            result.update(
                ok=True,
                scene_id=scene_attachment.id,
                png_id=png_attachment.id if png_attachment else None,
            )
            _logger.info(
                "excalidraw_for_odoo: saved '%s' (scene=%s png=%s) on %s#%s by %s",
                drawing_name,
                scene_attachment.id,
                png_attachment.id if png_attachment else None,
                res_model,
                res_id_int,
                request.env.user.login,
            )
        except (ValueError, AccessError, ValidationError, MissingError) as ex:
            _logger.warning("excalidraw_for_odoo: save refused: %s", str(ex))
            result = {"error": str(ex)}
        except Exception:
            _logger.exception("excalidraw_for_odoo: unexpected error saving")
            result = {
                "error": _("Unexpected error saving the drawing. Please try again.")
            }
        return result

    # ------------------------------------------------------------------
    # IR-ROUTE-2 — fetch a stored scene
    # ------------------------------------------------------------------

    @http.route(
        "/excalidraw/chatter/scene",
        auth="user",
        methods=["POST"],
        type="json",
    )
    def excalidraw_chatter_scene(self, attachment_id=None):
        """Return the stored scene text for a ``.excalidraw`` attachment."""
        result = {"scene": None}
        try:
            self._check_group()
            attachment_id_int = self._to_int(attachment_id)
            # sudo browse/read: marker rows are hard-denied for plain
            # users (CR-1 Option A platform constraint). The real-user
            # gates below — not attachment record rules — govern access.
            attachment = (
                request.env["ir.attachment"].sudo().browse(attachment_id_int).exists()
            )
            if not attachment:
                raise MissingError(_("The record does not exist or has been deleted."))
            data = attachment.read(["name", "res_model", "res_id", "datas"])[0]
            if not str(data["name"]).endswith(".excalidraw"):
                raise ValueError(
                    _("The attachment is not an Excalidraw scene document.")
                )
            # Generic model gate, identical message to the save route.
            model = self._chatter_model(data["res_model"])
            # Read gate on the host record, as the requesting user.
            record = model.browse(data["res_id"]).exists()
            if not record:
                raise MissingError(_("The record does not exist or has been deleted."))
            record.check_access_rights("read")
            record.check_access_rule("read")
            result = {
                "scene": base64.b64decode(data["datas"]).decode(
                    "utf-8", errors="replace"
                )
            }
            _logger.info(
                "excalidraw_for_odoo: fetched scene attachment %s for %s by %s",
                attachment_id_int,
                data["res_model"],
                request.env.user.login,
            )
        except (ValueError, AccessError, ValidationError, MissingError) as ex:
            _logger.warning("excalidraw_for_odoo: scene refused: %s", str(ex))
            result = {"error": str(ex)}
        except Exception:
            _logger.exception("excalidraw_for_odoo: unexpected error fetching scene")
            result = {
                "error": _("Unexpected error fetching the drawing. Please try again.")
            }
        return result

    # ------------------------------------------------------------------
    # IR-ROUTE-3 — list scene rows for the picker
    # ------------------------------------------------------------------

    @http.route(
        "/excalidraw/chatter/list",
        auth="user",
        methods=["POST"],
        type="json",
    )
    def excalidraw_chatter_list(self, res_model=None, res_id=None):
        """List the record's scene rows (id/name/write_date, newest first)."""
        result = {"ok": False, "drawings": []}
        try:
            self._check_group()
            model = self._chatter_model(res_model)
            res_id_int = self._to_int(res_id)
            record = model.browse(res_id_int).exists()
            if not record:
                raise MissingError(_("The record does not exist or has been deleted."))
            # Read gate on the host record, as the requesting user.
            record.check_access_rights("read")
            record.check_access_rule("read")
            # sudo search (marker rows are invisible to plain users);
            # "=ilike %.excalidraw" never matches the PNG twins, so the
            # listing is scene-only (half-pair tolerance by construction).
            rows = (
                request.env["ir.attachment"]
                .sudo()
                .search_read(
                    [
                        ("res_model", "=", res_model),
                        ("res_id", "=", res_id_int),
                        ("res_field", "=", SCENE_RES_FIELD),
                        ("name", "=ilike", "%.excalidraw"),
                    ],
                    ["name", "write_date"],
                    order="write_date desc",
                )
            )
            result = {
                "ok": True,
                "drawings": [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "write_date": row["write_date"],
                    }
                    for row in rows
                ],
            }
            _logger.info(
                "excalidraw_for_odoo: listed %s scene rows on %s#%s by %s",
                len(rows),
                res_model,
                res_id_int,
                request.env.user.login,
            )
        except (ValueError, AccessError, ValidationError, MissingError) as ex:
            _logger.warning("excalidraw_for_odoo: list refused: %s", str(ex))
            result = {"error": str(ex)}
        except Exception:
            _logger.exception("excalidraw_for_odoo: unexpected error listing")
            result = {
                "error": _("Unexpected error fetching the drawing. Please try again.")
            }
        return result
