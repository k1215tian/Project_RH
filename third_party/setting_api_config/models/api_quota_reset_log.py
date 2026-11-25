from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApiQuotaResetLog(models.Model):
    _name = 'api.quota.reset.log'
    _description = 'API Quota Reset History'
    _order = 'reset_date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, default='New')

    # Outbound quota (provider config) OR inbound quota (customer).
    config_id = fields.Many2one(
        'setting.api.conf', string='API Configuration',
        ondelete='restrict', index=True,
    )

    customer_id = fields.Many2one(
        'api.customer', string='API Customer',
        ondelete='restrict', index=True,
    )

    old_quota = fields.Integer(string='Remaining Before Reset')
    new_quota = fields.Integer(string='Remaining After Reset')

    reset_type = fields.Selection([
        ('manual', 'Manual'),
        ('daily', 'Automatic Daily'),
        ('monthly', 'Automatic Monthly'),
        ('yearly', 'Automatic Yearly'),
    ], string='Reset Type')

    reset_date = fields.Datetime(string='Reset Date', default=fields.Datetime.now)

    user_id = fields.Many2one(
        'res.users', string='Reset By', default=lambda self: self.env.user,
    )

    @api.constrains('config_id', 'customer_id')
    def _check_target(self):
        for rec in self:
            if bool(rec.config_id) == bool(rec.customer_id):
                raise ValidationError(_(
                    'A reset log must reference either an API configuration '
                    'or an API customer.'
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'api.quota.reset.log'
                ) or 'New'

        return super().create(vals_list)

    def write(self, vals):
        raise ValidationError(_(
            'Quota reset history cannot be modified.'
        ))

    def unlink(self):
        raise ValidationError(_(
            'Quota reset history cannot be deleted.'
        ))
