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

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class APIWebhookController(http.Controller):

    @http.route(
        '/api/webhook/<string:handler_code>/<string:config_code>',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False
    )
    def receive_webhook(
        self,
        handler_code,
        config_code,
        **kwargs
    ):

        try:

            # ----------------------------------------------------------
            # Read incoming JSON payload.
            # ----------------------------------------------------------

            payload = request.get_json_data()

            if not isinstance(payload, dict):
                return request.make_json_response({
                    'success': False,
                    'message': 'Invalid JSON payload.',
                }, status=400)

            # ----------------------------------------------------------
            # Find API configuration and webhook handler.
            # ----------------------------------------------------------

            Handler = request.env[
                'api.webhook.handler'
            ].sudo()

            handler = Handler.search([
                ('code', '=', handler_code),
                ('config_id.name', '=', config_code),
                ('active', '=', True),
                ('config_id.active', '=', True),
            ], limit=1)

            if not handler:
                return request.make_json_response({
                    'success': False,
                    'message': 'Webhook handler not found.',
                }, status=404)

            # ----------------------------------------------------------
            # Validate webhook authentication.
            #
            # Signature verification must be implemented using the
            # vendor-specific authentication mechanism.
            # ----------------------------------------------------------

            if not handler._validate_webhook(request.httprequest):
                return request.make_json_response({
                    'success': False,
                    'message': 'Unauthorized webhook request.',
                }, status=401)

            # ----------------------------------------------------------
            # Dispatch payload to integration-specific handler.
            # ----------------------------------------------------------

            result = handler.process_webhook(payload)

            return request.make_json_response({
                'success': True,
                'message': 'Webhook processed successfully.',
                'data': result or {},
            }, status=200)

        except Exception:

            _logger.exception(
                'Generic webhook processing failed.'
            )

            return request.make_json_response({
                'success': False,
                'message': 'Webhook processing failed.',
            }, status=500)
