from odoo import models, fields

class IrCron(models.Model):
    _name = 'ir.cron'
    _inherit = [
        'ir.cron',
        'mail.thread',
    ]

    _mail_post_access = 'read'

    active = fields.Boolean(tracking=True)
    user_id = fields.Many2one(
        tracking=True,
    )
    priority = fields.Integer(tracking=True)
    interval_number = fields.Integer(tracking=True)
    interval_type = fields.Selection(tracking=True)
    nextcall = fields.Datetime(tracking=True)
    lastcall = fields.Datetime(tracking=True)
