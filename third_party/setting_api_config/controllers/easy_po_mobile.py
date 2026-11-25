# -*- coding: utf-8 -*-
"""Sample outbound integration: send a confirmed PO to a vendor API.

The mobile client calls Odoo with its API key. Odoo reads the PO and sends a
normalized JSON payload to the vendor using ``setting.api.conf.call_api``.
"""

import logging
import time

from odoo.exceptions import UserError
from odoo.http import Controller, request, route

_logger = logging.getLogger(__name__)


class EasyPurchaseOrderMobileController(Controller):
    """Authenticated mobile entry point for sending a PO to its vendor."""

    @staticmethod
    def _json(body, status=200):
        return request.make_json_response(body, status=status)

    @staticmethod
    def _authenticate():
        api_key = request.httprequest.headers.get('X-API-Key', '')
        if not api_key:
            return False
        credential = request.env['api.credential'].sudo().authenticate_api_key(api_key)
        if credential:
            credential.action_mark_as_used(request.httprequest.remote_addr)
        return credential

    @staticmethod
    def _log_inbound(credential, endpoint, started, state, status,
                     message=False, units=0, billable=0):
        try:
            request.env['api.usage.log'].sudo().create({
                'direction': 'inbound',
                'customer_id': credential.customer_id.id,
                'credential_id': credential.id,
                'endpoint_id': endpoint.id,
                'endpoint': request.httprequest.path,
                'method': 'POST',
                'request_id': request.httprequest.headers.get('X-Request-ID') or False,
                'state': state,
                'status_code': status,
                'error_message': str(message)[:2000] if message else False,
                'duration_ms': max(0, int((time.monotonic() - started) * 1000)),
                'usage_units': units,
                'billable_units': billable,
            })
        except Exception:
            _logger.exception('Unable to record inbound PO API usage')

    @route('/api/v1/purchase/orders/<int:order_id>/send', type='http',
           auth='public', methods=['POST'], csrf=False, save_session=False)
    def send_purchase_order(self, order_id, **kwargs):
        """Send an existing confirmed PO to the configured vendor endpoint.

        Body: {"config_id": 12, "vendor_endpoint": "purchase/orders"}
        ``vendor_endpoint`` is a relative path; absolute URLs are rejected by
        ``setting.api.conf.call_api``. The config must belong to the API
        customer's company. The mobile caller cannot submit PO line values.
        """
        started = time.monotonic()
        credential = self._authenticate()
        if not credential:
            return self._json({'success': False, 'error': 'invalid_api_key'}, 401)

        customer = credential.customer_id
        if not customer.active:
            return self._json({'success': False, 'error': 'customer_inactive'}, 403)

        endpoint = request.env['api.endpoint'].sudo().search([
            ('code', '=', 'purchase_order_send'), ('active', '=', True),
        ], limit=1)
        if not endpoint or endpoint not in customer.endpoint_ids:
            return self._json({'success': False, 'error': 'endpoint_not_allowed'}, 403)

        httprequest = request.httprequest
        max_size = min(endpoint.max_request_size, 65536)
        if httprequest.content_length is not None and httprequest.content_length > max_size:
            return self._json({'success': False, 'error': 'payload_too_large'}, 413)
        raw_body = httprequest.get_data(cache=True)
        if len(raw_body) > max_size:
            return self._json({'success': False, 'error': 'payload_too_large'}, 413)
        if httprequest.mimetype != 'application/json':
            return self._json({'success': False, 'error': 'json_required'}, 415)
        try:
            payload = httprequest.get_json(silent=False)
        except (ValueError, TypeError):
            return self._json({'success': False, 'error': 'invalid_json'}, 400)
        if not isinstance(payload, dict):
            return self._json({'success': False, 'error': 'json_object_required'}, 400)

        config_id = payload.get('config_id')
        vendor_endpoint = payload.get('vendor_endpoint', 'purchase/orders')
        if isinstance(config_id, bool) or not isinstance(config_id, int):
            return self._json({'success': False, 'error': 'config_id_required'}, 400)
        if not isinstance(vendor_endpoint, str) or not vendor_endpoint.strip():
            return self._json({'success': False, 'error': 'invalid_vendor_endpoint'}, 400)

        # PO access is evaluated as the customer's configured execution user.
        execution_user = customer.user_id
        order = request.env['purchase.order'].with_user(execution_user).with_company(
            customer.company_id
        ).browse(order_id).exists()
        if not order:
            return self._json({'success': False, 'error': 'purchase_order_not_found'}, 404)
        try:
            order.check_access('read')
        except Exception:
            return self._json({'success': False, 'error': 'purchase_order_access_denied'}, 403)
        if order.company_id != customer.company_id:
            return self._json({'success': False, 'error': 'company_mismatch'}, 403)
        if order.state != 'purchase':
            return self._json({'success': False, 'error': 'purchase_order_not_confirmed'}, 409)

        config = request.env['setting.api.conf'].sudo().search([
            ('id', '=', config_id), ('active', '=', True),
            ('company_id', '=', customer.company_id.id),
        ], limit=1)
        if not config:
            return self._json({'success': False, 'error': 'api_configuration_not_found'}, 404)

        try:
            reserved = customer._reserve_units(endpoint.usage_units)
        except UserError as exc:
            self._log_inbound(credential, endpoint, started, 'error', 429, exc)
            return self._json({'success': False, 'error': 'quota_exceeded'}, 429)

        vendor = order.partner_id
        vendor_payload = {
            'purchase_order': {
                'name': order.name,
                'date_order': order.date_order.isoformat() if order.date_order else False,
                'vendor_reference': order.partner_ref or False,
                'currency': order.currency_id.name,
                'company': order.company_id.name,
                'vendor': {
                    'name': vendor.name,
                    'email': vendor.email or False,
                    'phone': vendor.phone or False,
                    'vat': vendor.vat or False,
                },
                'lines': [{
                    'product_code': line.product_id.default_code or False,
                    'product_name': line.product_id.display_name,
                    'quantity': line.product_qty,
                    'uom': line.product_uom.name,
                    'unit_price': line.price_unit,
                    'subtotal': line.price_subtotal,
                } for line in order.order_line if not line.display_type],
                'amount_untaxed': order.amount_untaxed,
                'amount_tax': order.amount_tax,
                'amount_total': order.amount_total,
            },
        }

        # Outbound credentials remain server-side. call_api enforces URL/SSL,
        # timeout, response size, outbound quota, and usage logging.
        try:
            result = config.with_company(customer.company_id).call_api(
                endpoint=vendor_endpoint,
                method='POST',
                json=vendor_payload,
                request_id=httprequest.headers.get('X-Request-ID') or False,
            )
        except UserError as exc:
            self._log_inbound(credential, endpoint, started, 'error', 400, exc,
                              units=endpoint.usage_units,
                              billable=reserved['billable_units'])
            return self._json({'success': False, 'error': 'api_call_rejected',
                               'message': str(exc)}, 400)
        if result.get('success'):
            self._log_inbound(credential, endpoint, started, 'success', 200,
                              units=endpoint.usage_units,
                              billable=reserved['billable_units'])
            return self._json({
                'success': True,
                'purchase_order': order.name,
                'vendor_status_code': result.get('status_code'),
                'vendor_response': result.get('response'),
                'request_id': result.get('request_id'),
            })

        self._log_inbound(credential, endpoint, started, 'error', 502,
                          result.get('response'), units=endpoint.usage_units,
                          billable=reserved['billable_units'])
        return self._json({
            'success': False,
            'error': 'vendor_api_failed',
            'vendor_status_code': result.get('status_code'),
            'vendor_response': result.get('response'),
            'request_id': result.get('request_id'),
        }, 502)


# ---------------------------------------------------------------------------
# MOBILE CLIENT USAGE NOTES
# ---------------------------------------------------------------------------
# Configure an active ``api.endpoint`` with code ``purchase_order_send`` and
# allow it for the API customer. Configure ``setting.api.conf`` with the
# vendor's base URL and authentication. The configuration's own outbound API
# key/Bearer/Basic/custom-header credentials are applied by ``call_api``.
# The API execution user must be able to read the PO and its company.
#
# Mobile -> Odoo request:
#   POST https://<odoo-host>/api/v1/purchase/orders/123/send
#   X-API-Key: <Odoo API credential>
#   Content-Type: application/json
#   Accept: application/json
#
# JSON body:
#   {
#     "config_id": 12,
#     "vendor_endpoint": "purchase/orders"
#   }
#
# ``config_id`` identifies the active outbound vendor configuration in the
# same company as the API customer. ``vendor_endpoint`` must be a relative
# path. The PO must already be confirmed (state ``purchase``); its lines and
# prices are read from Odoo, never accepted from the mobile request.
#
# Example with cURL:
#   curl -X POST 'https://<odoo-host>/api/v1/purchase/orders/123/send' \
#     -H 'X-API-Key: <Odoo API credential>' \
#     -H 'Content-Type: application/json' \
#     -H 'Accept: application/json' \
#     --data '{"config_id":12,"vendor_endpoint":"purchase/orders"}'
#
# Odoo responds with the vendor HTTP status, response body and request ID.
# Typical Odoo-side errors include 401 invalid_api_key, 403 endpoint_not_allowed,
# 404 purchase_order_not_found/api_configuration_not_found, 409 when the PO is
# not confirmed, and 502 vendor_api_failed.
