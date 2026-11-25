# -*- coding: utf-8 -*-
"""Example inbound API for mobile clients creating Odoo Sales Orders.

Configure an active ``api.endpoint`` with code ``sales_order_create`` and
include it in the API customer's Allowed API Endpoints. Mobile requests use
the credential in the ``X-API-Key`` header.
"""

import json
import logging
import math
import time

from odoo import _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import Controller, request, route

_logger = logging.getLogger(__name__)


class SampleSalesOrderController(Controller):
    """Sample authentication and inbound Sales Order routes."""

    @staticmethod
    def _json(body, status=200):
        return request.make_json_response(body, status=status)

    @staticmethod
    def _authenticate():
        key = request.httprequest.headers.get('X-API-Key', '')
        if not key:
            return False
        credential = request.env['api.credential'].sudo().authenticate_api_key(key)
        if not credential:
            return False
        credential.action_mark_as_used(request.httprequest.remote_addr)
        return credential

    @staticmethod
    def _write_usage(credential, endpoint, started, state, status, error=False,
                     units=0, billable=0):
        """Write inbound usage details; logging failure must not break the API."""
        try:
            customer = credential.customer_id
            request.env['api.usage.log'].sudo().create({
                'direction': 'inbound',
                'customer_id': customer.id,
                'credential_id': credential.id,
                'endpoint_id': endpoint.id,
                'endpoint': request.httprequest.path,
                'method': request.httprequest.method,
                'request_id': request.httprequest.headers.get('X-Request-ID') or False,
                'state': state,
                'status_code': status,
                'error_message': str(error)[:2000] if error else False,
                'duration_ms': max(0, int((time.monotonic() - started) * 1000)),
                'usage_units': units,
                'billable_units': billable,
            })
        except Exception:
            _logger.exception('Unable to record inbound API usage')

    @route('/api/v1/authenticate', type='http', auth='public', methods=['POST'],
           csrf=False, save_session=False)
    def authenticate(self, **kwargs):
        """Validate an API key and return its nonsecret client identity.

        This is API-client authentication, not an Odoo end-user password login.
        The client must send the key again on every API request.
        """
        credential = self._authenticate()
        if not credential:
            return self._json({'success': False, 'error': 'invalid_api_key'}, 401)
        customer = credential.customer_id
        return self._json({
            'success': True,
            'customer': {'id': customer.id, 'code': customer.code,
                         'name': customer.name},
            'credential': {'id': credential.id, 'name': credential.name,
                           'expires_at': credential.expires_at},
        })

    @route('/api/v1/sales/orders', type='http', auth='public', methods=['POST'],
           csrf=False, save_session=False)
    def create_sales_order(self, **kwargs):
        started = time.monotonic()
        httprequest = request.httprequest
        credential = self._authenticate()
        if not credential:
            return self._json({'success': False, 'error': 'invalid_api_key'}, 401)

        customer = credential.customer_id
        if not customer.active:
            return self._json({'success': False, 'error': 'customer_inactive'}, 403)

        endpoint = request.env['api.endpoint'].sudo().search([
            ('code', '=', 'sales_order_create'), ('active', '=', True),
        ], limit=1)
        if not endpoint or endpoint not in customer.endpoint_ids:
            return self._json({'success': False, 'error': 'endpoint_not_allowed'}, 403)

        max_size = min(endpoint.max_request_size, 1024 * 1024)
        if httprequest.content_length is not None and httprequest.content_length > max_size:
            return self._json({'success': False, 'error': 'payload_too_large'}, 413)
        raw_body = httprequest.get_data(cache=True)
        if len(raw_body) > max_size:
            return self._json({'success': False, 'error': 'payload_too_large'}, 413)
        if httprequest.mimetype != 'application/json':
            return self._json({'success': False, 'error': 'json_required'}, 415)
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except (ValueError, TypeError, UnicodeDecodeError):
            return self._json({'success': False, 'error': 'invalid_json'}, 400)
        if not isinstance(payload, dict):
            return self._json({'success': False, 'error': 'json_object_required'}, 400)

        partner_id = payload.get('partner_id')
        lines = payload.get('lines')
        if (isinstance(partner_id, bool) or not isinstance(partner_id, int)
                or not isinstance(lines, list) or not lines):
            return self._json({'success': False,
                               'error': 'partner_id_and_nonempty_lines_required'}, 400)

        order_lines = []
        for line in lines:
            if not isinstance(line, dict):
                return self._json({'success': False, 'error': 'invalid_order_line'}, 400)
            product_id = line.get('product_id')
            quantity = line.get('quantity')
            if (isinstance(product_id, bool) or not isinstance(product_id, int)
                    or isinstance(quantity, bool) or not isinstance(quantity, (int, float))
                    or not math.isfinite(quantity) or quantity <= 0):
                return self._json({'success': False, 'error': 'invalid_order_line'}, 400)
            order_lines.append((0, 0, {
                'product_id': product_id,
                'product_uom_qty': quantity,
            }))

        try:
            reserved = customer._reserve_units(endpoint.usage_units)
        except UserError as exc:
            self._write_usage(credential, endpoint, started, 'error', 429, exc)
            return self._json({'success': False, 'error': 'quota_exceeded'}, 429)

        try:
            execution_env = request.env['sale.order'].with_user(
                customer.user_id
            ).with_company(customer.company_id)
            with request.env.cr.savepoint():
                order = execution_env.create({
                    'partner_id': partner_id,
                    'company_id': customer.company_id.id,
                    'order_line': order_lines,
                })
            self._write_usage(credential, endpoint, started, 'success', 201,
                              units=endpoint.usage_units,
                              billable=reserved['billable_units'])
            return self._json({
                'success': True,
                'sales_order': {'id': order.id, 'name': order.name,
                                'state': order.state,
                                'amount_total': order.amount_total,
                                'currency': order.currency_id.name},
            }, 201)
        except (AccessError, UserError, ValidationError) as exc:
            self._write_usage(credential, endpoint, started, 'error', 400, exc,
                              units=endpoint.usage_units,
                              billable=reserved['billable_units'])
            return self._json({'success': False, 'error': 'request_rejected',
                               'message': str(exc)}, 400)
        except Exception:
            _logger.exception('Mobile Sales Order API failed')
            self._write_usage(credential, endpoint, started, 'failed', 500,
                              _('Internal server error'),
                              units=endpoint.usage_units,
                              billable=reserved['billable_units'])
            return self._json({'success': False, 'error': 'internal_server_error'}, 500)


# ---------------------------------------------------------------------------
# MOBILE CLIENT USAGE NOTES
# ---------------------------------------------------------------------------
#
# 1. Configure an active ``api.endpoint`` record:
#       Code:               sales_order_create
#       HTTP Method:        POST
#       Path:               /api/v1/sales/orders
#       Handler Key:        sample.sales.order.create (informational here)
#       Usage Units:        number of quota units charged per request
#       Max Request Size:   request body limit in bytes (up to 1 MB)
#    Add this endpoint to the API customer's Allowed API Endpoints. Assign that
#    customer an API Execution User with permission to create sale.order and
#    read the requested contacts and products.
#
# 2. Validate the API key (optional client-side connection check):
#       POST https://<odoo-host>/api/v1/authenticate
#       X-API-Key: <plaintext key issued in Odoo>
#       Content-Type: application/json
#    The response identifies the API customer. This route does not issue an
#    end-user session token; send the API key with every API request.
#
# 3. Create a Sales Order:
#       POST https://<odoo-host>/api/v1/sales/orders
#       X-API-Key: <plaintext key issued in Odoo>
#       Content-Type: application/json
#       Accept: application/json
#
#    JSON body (partner_id and product_id are Odoo database record IDs):
#    {
#      "partner_id": 42,
#      "lines": [
#        {"product_id": 15, "quantity": 2},
#        {"product_id": 27, "quantity": 1.5}
#      ]
#    }
#
#    Successful response (HTTP 201):
#    {
#      "success": true,
#      "sales_order": {
#        "id": 123,
#        "name": "S00042",
#        "state": "draft",
#        "amount_total": 150.0,
#        "currency": "IDR"
#      }
#    }
#
#    Example using cURL:
#      curl -X POST 'https://<odoo-host>/api/v1/sales/orders' \
#        -H 'X-API-Key: <plaintext key>' \
#        -H 'Content-Type: application/json' \
#        -H 'Accept: application/json' \
#        --data '{"partner_id":42,"lines":[{"product_id":15,"quantity":2}]}'
#
#    Common errors: 401 invalid_api_key, 403 endpoint_not_allowed,
#    413 payload_too_large, 415 json_required, and 429 quota_exceeded.
#    Always call the production endpoint over HTTPS and keep the API key in
#    protected client storage; do not embed a shared production key in a
#    publicly distributed mobile application.
