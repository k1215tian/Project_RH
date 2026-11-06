from odoo import models, fields, api, _


class ApiUsageLog(models.Model):
    _name = 'api.usage.log'
    _description = 'API Usage Log'
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference',
        default='New',
        readonly=True
    )

    config_id = fields.Many2one(
        'setting.api.conf',
        string='API Configuration',
        required=True,
        ondelete='restrict'
    )

    company_id = fields.Many2one(
        related='config_id.company_id',
        string='Company',
        store=True
    )

    endpoint = fields.Char(
        string='Endpoint'
    )

    method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('PATCH', 'PATCH'),
        ('DELETE', 'DELETE'),
    ], string='Method')

    status_code = fields.Integer(
        string='HTTP Status Code'
    )

    state = fields.Selection([
        ('success', 'Success'),
        ('error', 'HTTP Error'),
        ('failed', 'Connection Failed'),
    ], string='Status', default='failed')

    response_body = fields.Text(
        string='Response'
    )

    error_message = fields.Text(
        string='Error Message'
    )

    input_tokens = fields.Integer(
        string='Input Tokens',
        default=0
    )

    output_tokens = fields.Integer(
        string='Output Tokens',
        default=0
    )

    thinking_tokens = fields.Integer(
        string='Thinking Tokens',
        default=0
    )

    total_tokens = fields.Integer(
        string='Total Tokens',
        compute='_compute_total_tokens',
        store=True
    )

    @api.depends(
        'input_tokens',
        'output_tokens',
        'thinking_tokens'
    )
    def _compute_total_tokens(self):
        for rec in self:
            rec.total_tokens = (
                rec.input_tokens
                + rec.output_tokens
                + rec.thinking_tokens
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'api.usage.log'
                ) or 'New'

        return super().create(vals_list)
