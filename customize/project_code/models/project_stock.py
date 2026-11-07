# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_project = fields.Boolean(
        'Project',
        default=False)
    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',)


class StockMove(models.Model):
    _inherit = 'stock.move'

    project_id = fields.Many2one(
        comodel_name='project.project',
        string='Project',
        ondelete='cascade',
    )
    task_id = fields.Many2one(
        'project.task',
        string='Task',
        domain="[('project_id','=',project_id)]",
        store=True
    )
