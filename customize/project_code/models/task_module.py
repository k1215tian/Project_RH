# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class TaskModule(models.Model):
    _name = 'task.module'
    _description = 'Task Module'

    name = fields.Char('Module')
    code = fields.Char('Code')
    parent_id = fields.Many2one('task.module', 'Parent')
    child_ids = fields.One2many('task.module', 'parent_id', 'Sub Module')
    color = fields.Integer(
        string='Color Index',
        export_string_translation=False)
    active = fields.Boolean(
        'Active',
        default=True,
        help="Set false to hide this module without removing it.")

    _sql_constraints = [
        (
            'task_module_code_unique',
            'unique(code)',
            'Code must be unique!'
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].upper()
        return super().write(vals)

    @api.depends('name', 'code', 'parent_id.code')
    def _compute_display_name(self):
        for rec in self:
            code = (rec.code or '').upper()

            if rec.parent_id:
                parent_code = (rec.parent_id.code or '').upper()
                rec.display_name = f'[{parent_code}/{code}] {rec.name or ""}'
            else:
                rec.display_name = f'[{code}] {rec.name or ""}'

    @api.constrains('code')
    def _check_code(self):
        for rec in self:
            if not rec.code:
                continue

            rec.code = rec.code.upper()

            duplicate = self.search([
                ('id', '!=', rec.id),
                ('code', '=', rec.code.upper())
            ], limit=1)

            if duplicate:
                raise ValidationError(
                    _("Code '%s' already exists.") % rec.code.upper()
                )
 