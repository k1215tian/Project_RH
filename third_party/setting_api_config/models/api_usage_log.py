# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApiUsageLog(models.Model):
    _name = 'api.usage.log'
    _description = 'API Usage Log'
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Reference', default='New', readonly=True, copy=False, index=True,
    )

    request_id = fields.Char(
        string='Request ID', readonly=True, copy=False, index=True)

    direction = fields.Selection(
        [
            ('inbound', 'Inbound (Customer -> Odoo)'),
            ('outbound', 'Outbound (Odoo -> Provider)'),
        ],
        string='Direction',
        required=True,
        default='outbound',
        index=True,
        copy=False,
    )

    customer_id = fields.Many2one(
        'api.customer', string='API Customer',
        ondelete='restrict', index=True, copy=False,
    )

    credential_id = fields.Many2one(
        'api.credential', string='API Credential',
        ondelete='restrict', index=True, copy=False,
    )

    # Not required: inbound requests have a customer but no provider config.
    config_id = fields.Many2one(
        'setting.api.conf', string='API Configuration',
        ondelete='restrict', index=True, copy=False,
    )

    company_id = fields.Many2one(
        'res.company', string='Company',
        compute='_compute_company_id', store=True, readonly=True, index=True,
    )

    endpoint_id = fields.Many2one(
        'api.endpoint', string='API Endpoint',
        ondelete='restrict', index=True, copy=False,
    )

    endpoint = fields.Char(string='Endpoint', index=True, copy=False)

    method = fields.Selection(
        [('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'),
         ('PATCH', 'PATCH'), ('DELETE', 'DELETE')],
        string='HTTP Method', index=True, copy=False,
    )

    @api.depends('config_id.company_id', 'customer_id.company_id')
    def _compute_company_id(self):
        for record in self:
            record.company_id = (
                record.config_id.company_id or record.customer_id.company_id
            )

    status_code = fields.Integer(
        string='HTTP Status Code', index=True, copy=False)

    state = fields.Selection(
        [('success', 'Success'), ('error', 'HTTP Error'),
         ('failed', 'Connection Failed')],
        string='Status', default='failed', required=True, index=True, copy=False,
    )

    response_body = fields.Text(string='Response', copy=False)
    error_message = fields.Text(string='Error Message', copy=False)
    duration_ms = fields.Integer(string='Duration (ms)', default=0, copy=False)

    external_reference = fields.Char(
        string='Provider Reference', index=True, copy=False,
        help='Provider-side id used to match an incoming callback.',
    )

    callback_state = fields.Selection(
        [
            ('none', 'No Callback Expected'),
            ('pending', 'Waiting for Callback'),
            ('received', 'Callback Received'),
            ('failed', 'Callback Failed'),
        ],
        string='Callback Status', default='none', index=True, copy=False,
    )

    callback_ids = fields.One2many(
        'api.callback.log', 'usage_log_id', string='Callbacks')

    usage_units = fields.Integer(string='Usage Units', default=0, copy=False)
    billable_units = fields.Integer(
        string='Billable Units', default=0, copy=False)

    unit_price = fields.Monetary(
        string='Unit Price', currency_field='currency_id', default=0.0, copy=False,
    )

    usage_charge = fields.Monetary(
        string='Usage Charge', currency_field='currency_id',
        compute='_compute_usage_charge', store=True, copy=False,
    )

    # Outbound logs have no customer -> fall back to the company currency.
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        compute='_compute_currency_id', store=True, readonly=True,
    )

    @api.depends('customer_id.currency_id', 'company_id.currency_id')
    def _compute_currency_id(self):
        for record in self:
            record.currency_id = (
                record.customer_id.currency_id or record.company_id.currency_id
            )

    @api.depends('billable_units', 'unit_price')
    def _compute_usage_charge(self):
        for record in self:
            record.usage_charge = record.billable_units * record.unit_price

    input_tokens = fields.Integer(string='Input Tokens', default=0, copy=False)
    output_tokens = fields.Integer(
        string='Output Tokens', default=0, copy=False)
    thinking_tokens = fields.Integer(
        string='Thinking Tokens', default=0, copy=False)

    total_tokens = fields.Integer(
        string='Total Tokens', compute='_compute_total_tokens', store=True, copy=False,
    )

    @api.depends('input_tokens', 'output_tokens', 'thinking_tokens')
    def _compute_total_tokens(self):
        for record in self:
            record.total_tokens = (
                record.input_tokens + record.output_tokens + record.thinking_tokens
            )

    @api.constrains(
        'usage_units', 'billable_units', 'unit_price',
        'input_tokens', 'output_tokens', 'thinking_tokens', 'duration_ms',
    )
    def _check_usage_values(self):
        for record in self:
            if record.usage_units < 0:
                raise ValidationError(_('Usage units cannot be negative.'))
            if record.billable_units < 0:
                raise ValidationError(_('Billable units cannot be negative.'))
            if record.unit_price < 0:
                raise ValidationError(_('Unit price cannot be negative.'))
            if record.duration_ms < 0:
                raise ValidationError(
                    _('Request duration cannot be negative.'))
            if (
                record.input_tokens < 0
                or record.output_tokens < 0
                or record.thinking_tokens < 0
            ):
                raise ValidationError(_('Token usage cannot be negative.'))

    @api.constrains('direction', 'config_id', 'customer_id')
    def _check_direction_links(self):
        for record in self:
            if record.direction == 'outbound' and not record.config_id:
                raise ValidationError(
                    _('Outbound logs require an API configuration.'))
            if record.direction == 'inbound' and not record.customer_id:
                raise ValidationError(
                    _('Inbound logs require an API customer.'))

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []

        for vals in vals_list:
            vals = vals.copy()

            if vals.get('name', 'New') == 'New':
                sequence = self.env['ir.sequence'].next_by_code(
                    'api.usage.log')

                if not sequence:
                    raise ValidationError(_(
                        'API Usage Log sequence is not configured. '
                        'Please configure sequence code: api.usage.log'
                    ))

                vals['name'] = sequence

            prepared_vals.append(vals)

        return super().create(prepared_vals)
