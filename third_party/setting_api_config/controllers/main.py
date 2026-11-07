# ----------------------------------------------------------------------
#  Generic API Webhook Controller
#
#  This controller handles incoming webhook requests from external
#  systems.
#
#  Responsibilities:
#  - Receive webhook requests.
#  - Validate request payload.
#  - Identify the webhook handler.
#  - Dispatch payload to the appropriate integration module.
#  - Return standardized JSON responses.
#
#  This controller does not contain business-specific logic.
# ----------------------------------------------------------------------


import json 
import logging
# import hashlib
# import hmac

from odoo import http, _ 
from odoo.http import request, Response
_logger = logging.getLogger(__name__)B

class GenericWebhookController(http.Controller):

    MAX_PAYLOAD_SIZE = 1024 * 1024  # 1 M
    # ---------------------------------------------------------
    # WEBHOOK ENDPOINT
    # ---------------------------------------------------------

    @http.route(
        "/api/webhook/<string:handler_code>/<string:config_code>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def receive_webhook(
        self,
        handler_code,
        config_code,
        **kwargs,
    ):

        # -----------------------------------------------------
        # 1. READ RAW REQUEST
        # -----------------------------------------------------

        http_request = request.httprequest

        if http_request.content_length is not None:
            if http_request.content_length > self.MAX_PAYLOAD_SIZE:
                return self._response(
                    {
                        "success": False,
                        "message": "Payload too large.",
                    },
                    413,
                )

        raw_body = http_request.get_data(cache=True)

        if len(raw_body) > self.MAX_PAYLOAD_SIZE:
            return self._response(
                {
                    "success": False,
                    "message": "Payload too large.",
                },
                413,
            )

        headers = dict(http_request.headers)

        # -----------------------------------------------------
        # 2. VALIDATE CONTENT TYPE
        # -----------------------------------------------------

        content_type = http_request.mimetype

        if content_type != "application/json":
            return self._response(
                {
                    "success": False,
                    "message": "Content-Type must be application/json.",
                },
                415,
            )

        # -----------------------------------------------------
        # 3. PARSE JSON
        # -----------------------------------------------------

        try:
            payload = json.loads(
                raw_body.decode("utf-8")
            )

        except (ValueError, UnicodeDecodeError):

            return self._response(
                {
                    "success": False,
                    "message": "Invalid JSON payload.",
                },
                400,
            )

        if not isinstance(payload, dict):
            return self._response(
                {
                    "success": False,
                    "message": "JSON object expected.",
                },
                400,
            )

        # -----------------------------------------------------
        # 4. FIND CONFIGURATION
        # -----------------------------------------------------

        Config = request.env[
            "setting.api.conf"
        ].sudo()

        config = Config.search(
            [
                ("code", "=", config_code),
                ("active", "=", True),
            ],
            limit=2,
        )

        if len(config) != 1:
            return self._response(
                {
                    "success": False,
                    "message": "Invalid configuration.",
                },
                404,
            )

        # -----------------------------------------------------
        # 5. FIND WEBHOOK HANDLER
        # -----------------------------------------------------

        Handler = request.env[
            "api.webhook.handler"
        ].sudo()

        handler = Handler.search(
            [
                ("code", "=", handler_code),
                ("active", "=", True),
                ("company_id", "=", config.company_id.id),
                ("config_ids", "in", config.id),
            ],
            limit=1,
        )

        if not handler:
            return self._response(
                {
                    "success": False,
                    "message": "Webhook handler not found.",
                },
                404,
            )

        # -----------------------------------------------------
        # 6. AUTHENTICATION
        # -----------------------------------------------------

        try:
            authenticated = handler.validate_authentication(
                headers,
                payload,
                raw_body,
            )

        except Exception:

            _logger.exception(
                "Webhook authentication error. Handler: %s",
                handler.code,
            )

            return self._response(
                {
                    "success": False,
                    "message": "Authentication service unavailable.",
                },
                500,
            )

        if not authenticated:
            return self._response(
                {
                    "success": False,
                    "message": "Invalid authentication.",
                },
                401,
            )

        # -----------------------------------------------------
        # 7. VALIDATE PAYLOAD
        # -----------------------------------------------------

        try:
            handler.validate_payload(payload)

        except Exception:

            _logger.warning(
                "Webhook payload validation failed. Handler: %s",
                handler.code,
                exc_info=True,
            )

            return self._response(
                {
                    "success": False,
                    "message": "Invalid webhook payload.",
                },
                400,
            )

        # -----------------------------------------------------
        # 8. IDENTIFY EVENT
        # -----------------------------------------------------

        event_id = (
            headers.get("X-Event-ID")
            or payload.get("event_id")
            or payload.get("id")
        )

        if event_id is None or not str(event_id).strip():
            return self._response(
                {
                    "success": False,
                    "message": "Missing event identifier.",
                },
                400,
            )

        event_id = str(event_id).strip()

        # -----------------------------------------------------
        # 9. CHECK IDEMPOTENCY
        # -----------------------------------------------------

        WebhookLog = request.env[
            "api.webhook.log"
        ].sudo()

        domain = [
            ("handler_id", "=", handler.id),
            ("config_id", "=", config.id),
            ("event_id", "=", event_id),
        ]

        existing = WebhookLog.search(
            domain,
            limit=1,
        )

        if existing:
            return self._response(
                {
                    "success": True,
                    "message": "Event already received.",
                    "event_id": event_id,
                    "log_id": existing.id,
                    "status": existing.status,
                },
                200,
            )

        # -----------------------------------------------------
        # 10. CREATE WEBHOOK LOG
        # -----------------------------------------------------

        try:

            log = WebhookLog.create(
                {
                    "name": "%s - %s" % (
                        handler.code,
                        event_id,
                    ),
                    "handler_id": handler.id,
                    "config_id": config.id,
                    "event_id": event_id,
                    "idempotency_key": event_id,
                    "request_headers": json.dumps(
                        self._sanitize_headers(headers)
                    ),
                    "request_payload": json.dumps(
                        payload,
                        ensure_ascii=False,
                        default=str,
                    ),
                    "status": "queued",
                }
            )

        except Exception:

            # A concurrent request may have created
            # the same event in the meantime.

            existing = WebhookLog.search(
                domain,
                limit=1,
            )

            if existing:
                return self._response(
                    {
                        "success": True,
                        "message": "Event already received.",
                        "event_id": event_id,
                        "log_id": existing.id,
                        "status": existing.status,
                    },
                    200,
                )

            _logger.exception(
                "Failed to create webhook log. Handler: %s",
                handler.code,
            )

            return self._response(
                {
                    "success": False,
                    "message": "Unable to accept webhook.",
                },
                500,
            )

        # -----------------------------------------------------
        # 11. ACCEPT WEBHOOK
        # -----------------------------------------------------

        return self._response(
            {
                "success": True,
                "message": "Webhook accepted.",
                "event_id": event_id,
                "log_id": log.id,
                "status": "queued",
            },
            202,
        )

    # ---------------------------------------------------------
    # JSON RESPONSE
    # ---------------------------------------------------------

    @staticmethod
    def _response(data, status=200):

        return Response(
            json.dumps(
                data,
                ensure_ascii=False,
            ),
            status=status,
            content_type="application/json; charset=utf-8",
        )

    # ---------------------------------------------------------
    # HEADER SANITIZATION
    # ---------------------------------------------------------

    @staticmethod
    def _sanitize_headers(headers):

        sensitive_headers = {
            "authorization",
            "proxy-authorization",
            "x-api-key",
            "api-key",
            "x-webhook-secret",
            "x-auth-token",
            "cookie",
            "set-cookie",
        }

        return {
            key: (
                "***REDACTED***"
                if key.lower() in sensitive_headers
                else value
            )
            for key, value in headers.items()
        }
