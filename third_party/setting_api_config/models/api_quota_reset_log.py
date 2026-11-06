from odoo import models, fields, api


class ApiQuotaResetLog(models.Model):
    _name = 'api.quota.reset.log'
    _description = 'API Quota Reset History'
    _order = 'reset_date desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        default='New'
    )

    config_id = fields.Many2one(
        'setting.api.conf',
        string='API Configuration',
        required=True,
        ondelete='restrict'
    )

    old_quota = fields.Integer(
        string='Previous Quota'
    )

    new_quota = fields.Integer(
        string='New Quota'
    )

    reset_type = fields.Selection([
        ('manual', 'Manual'),
        ('daily', 'Automatic Daily'),
        ('monthly', 'Automatic Monthly'),
    ], string='Reset Type')

    reset_date = fields.Datetime(
        string='Reset Date',
        default=fields.Datetime.now
    )

    user_id = fields.Many2one(
        'res.users',
        string='Reset By',
        default=lambda self: self.env.user
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'api.quota.reset.log'
                ) or 'New'

        return super().create(vals_list)
