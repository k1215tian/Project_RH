# -*- coding: utf-8 -*-

import hashlib
import hmac
import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ApiCallbackLog(models.Model):
    _name = 'api.callback.log'
    _description = 'API Callback Log'
    _order = 'received_at desc, id desc'

    name = fields.Char(string='Reference', readonly=True, default='New', copy=False)

    config_id = fields.Many2one(
        'setting.api.conf', string='API Configuration',
        required=True, ondelete='restrict', index=True,
    )

    usage_log_id = fields.Many2one(
        'api.usage.log', string='Usage Log', ondelete='set null', index=True,
    )

    request_id = fields.Char(index=True)
    external_reference = fields.Char(index=True)
    received_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    remote_ip = fields.Char(string='Remote IP', readonly=True)

    state = fields.Selection(
        [('matched', 'Matched'), ('unmatched', 'Unmatched'), ('failed', 'Failed')],
        default='unmatched', index=True,
    )

    payload = fields.Text(string='Payload', readonly=True)
    error_message = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'api.callback.log'
                ) or 'New'
        return super().create(vals_list)

    @api.model
    def _extract_references(self, payload):
        """Return (request_id, external_reference) from the parsed payload."""
        if isinstance(payload, dict):
            request_id = payload.get('request_id')
            external = payload.get('id') or payload.get('reference')
            return (
                str(request_id)[:255] if request_id else False,
                str(external)[:255] if external else False,
            )
        return False, False

    @api.model
    def _find_usage_log(self, config, request_id, external_reference):
        Usage = self.env['api.usage.log'].sudo()
        base = [('config_id', '=', config.id), ('direction', '=', 'outbound')]
        log = Usage.browse()

        if request_id:
            log = Usage.search(base + [('request_id', '=', request_id)], limit=1)

        if not log and external_reference:
            log = Usage.search(
                base + [('external_reference', '=', external_reference)], limit=1,
            )

        return log

    @api.model
    def _receive(self, config, raw_body, signature, remote_ip=False):
        """
        Verify the HMAC-SHA256 signature, store the callback and update the
        matching usage log. Returns the callback record, or False when the
        signature is invalid (nothing is stored for unauthenticated calls).
        """

        config = config.sudo()
        secret = config.callback_secret

        if not secret:
            _logger.warning('Callback secret not configured: config_id=%s', config.id)
            return False

        expected = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected, (signature or '').strip().lower()):
            _logger.warning(
                'Invalid callback signature: config_id=%s ip=%s', config.id, remote_ip,
            )
            return False

        text = raw_body.decode('utf-8', errors='replace')

        try:
            payload = json.loads(text)
        except ValueError:
            payload = None

        request_id, external_reference = self._extract_references(payload)
        usage_log = self._find_usage_log(config, request_id, external_reference)

        callback = self.sudo().create({
            'config_id': config.id,
            'usage_log_id': usage_log.id or False,
            'request_id': request_id,
            'external_reference': external_reference,
            'remote_ip': remote_ip,
            'state': 'matched' if usage_log else 'unmatched',
            'payload': text[:20000],
        })

        if usage_log:
            usage_log.write({'callback_state': 'received'})

        return callback
