# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _inherit = 'project.task'

    project_type_id = fields.Many2one(
        string="Project Type",
        comodel_name='project.type', track_visibility='onchange')
    code = fields.Char(string="Task Code")
    task_module_id = fields.Many2one(
        string="Project Module",
        comodel_name='task.module', track_visibility='onchange')
    type_task = fields.Selection([
        ('software', 'Software Development'),
        ('hardware', 'Hardware & Infrastructure'),
        ('services', 'Managed Services'),
        ('consulting', 'Consulting'),
        ('maintenance', 'Maintenance & Support'),
        ('others', 'Others')
    ],
        string="Type task",
        help="Spesifikasi type task untuk project ini.")
    level_class = fields.Selection(
        [
            ('low', 'low'),
            ('normal', 'Normal'),
            ('urgent', 'Urgent')
        ],
        string="Leveling task",
        default="normal",
        track_visibility='onchange',
        help="Spesifikasi type task untuk project ini.")
    is_bug = fields.Boolean(
        'is Bug',
        default=False)
    diviculty_level = fields.Selection(
        [
            ('0', '0'),
            ('1', '1'),
            ('2', '2'),
            ('3', '3'),
            ('4', '4'),
            ('5', '5'),
            ('6', '6'),
        ],
        string="Diviculty",
        track_visibility='onchange')
    mr_reqquest = fields.Char(
        string="Git Merging Reqquest",
        track_visibility='onchange',
        help="Link git Merging Reuest")
    mr_state = fields.Selection(
        [
            ('none', 'None'),
            ('conflict', 'Conflict'),
            ('staging', 'Staging'),
            ('prod', 'Prodution'),
        ],
        string="MR State",
        default="none",
        track_visibility='onchange',
        help="Merging Reuest Status")
