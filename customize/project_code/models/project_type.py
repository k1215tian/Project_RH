# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProjectType(models.Model):
    _name = 'project.type'
    _description = 'Project Type'

    name = fields.Char('Name')
    active = fields.Boolean(
        'Active',
        default=True,
        help="If unchecked, it will allow you "
        "to hide the type project without removing it.")
    code = fields.Char(
        string='Code',
        size=3)
    color = fields.Integer(
        string='Color Index',
        export_string_translation=False)
    description = fields.Text()
    sequence_id = fields.Many2one(comodel_name='ir.sequence')
    income_account_id = fields.Many2one(
        comodel_name='account.account', string="Income Account")
    salary_account_id = fields.Many2one(
        comodel_name='account.account', string="Salaries Account")
    accrued_expense_id = fields.Many2one(
        comodel_name='account.account', string="Expense Account")
    discount_account_id = fields.Many2one(
        comodel_name='account.account', string="Discount Account")
    cost_account_ids = fields.Many2many(
        'account.account', string="Cost of Sales Account")
    overhead_account_id = fields.Many2one(
        comodel_name='account.account', string="Overhead Account")
