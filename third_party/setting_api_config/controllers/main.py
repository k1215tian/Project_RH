import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

MAX_CALLBACK_SIZE = 1024 * 1024  # 1 MB


class ApiCallbackController(http.Controller):

    @http.route(
        '/api_management/callback/<string:token>',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def receive_callback(self, token, **kwargs):
        httprequest = request.httprequest

        length = httprequest.content_length
        if length is None:
            return request.make_json_response({'error': 'length_required'}, status=411)
        if length > MAX_CALLBACK_SIZE:
            return request.make_json_response({'error': 'payload_too_large'}, status=413)

        config = request.env['setting.api.conf'].sudo().search([
            ('callback_token', '=', token),
            ('active', '=', True),
        ], limit=1)

        if not config:
            return request.make_json_response({'error': 'not_found'}, status=404)

        callback = request.env['api.callback.log'].sudo()._receive(
            config,
            httprequest.get_data(),
            httprequest.headers.get('X-Signature', ''),
            httprequest.remote_addr,
        )

        if not callback:
            return request.make_json_response({'error': 'invalid_signature'}, status=401)

        return request.make_json_response({'status': 'ok'})
