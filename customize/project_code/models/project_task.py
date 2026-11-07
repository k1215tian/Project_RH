# -*- coding: utf-8 -*-
import logging
import math

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _inherit = 'project.task'

    project_type_id = fields.Many2one(
        string="Project Type",
        comodel_name="project.type",
        track_visibility='onchange')
    code = fields.Char(string="Task Code")
    task_module_id = fields.Many2one(
        string="Project Module",
        comodel_name="task.module",
        track_visibility='onchange')
    module_id = fields.Many2one(
        "ir.model",
        string="Module",)
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
        string="Git Merging Request",
        track_visibility='onchange',
        help="Link git Merging Reuest")
    mr_reqquest_conflict = fields.Char(
        string="Git Merging Request Conflict",
        track_visibility='onchange',
        help="Link git Merging Reuest Conflict")
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

    planned_mandays = fields.Float(
        string='Planned Mandays',
        default=0.0,
        tracking=True,
        help='Estimated working days for this task.'
    )

    timesheet_slot_ids = fields.One2many(
        'project.task.timesheet.slot',
        'task_id',
        string='Timesheet Slots'
    )

    timesheet_slot_count = fields.Integer(
        string='Timesheet Slots',
        compute='_compute_timesheet_slot_count'
    )

    @api.depends('timesheet_slot_ids')
    def _compute_timesheet_slot_count(self):
        for task in self:
            task.timesheet_slot_count = len(
                task.timesheet_slot_ids
            )

    def action_generate_timesheet(self):
        for task in self:

            if task.planned_mandays <= 0:
                raise UserError(
                    _('Planned Mandays must be greater than zero.')
                )

            # Calculate number of records
            total_records = math.ceil(
                task.planned_mandays
            )

            existing_records = len(
                task.timesheet_slot_ids
            )

            records_to_create = (
                total_records - existing_records
            )

            if records_to_create <= 0:
                continue

            values = []

            for index in range(records_to_create):
                values.append({
                    'task_id': task.id,
                    'sequence': existing_records + index + 1,
                    'name': task.name,
                    'state': 'draft',
                })

            self.env[
                'project.task.timesheet.slot'
            ].create(values)

        return True
