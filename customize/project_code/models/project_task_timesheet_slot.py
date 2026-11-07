
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class TaskTimesheetSlot(models.Model):
    _name = 'project.task.timesheet.slot'
    _description = 'Task Timesheet Slot'
    _order = 'task_id, sequence, id'

    name = fields.Char(
        string='Description',
        compute='_compute_generate_name',
        store=True,
        readonly=False,
    )

    sequence = fields.Integer(
        string='Sequence',
        default=10
    )

    task_id = fields.Many2one(
        'project.task',
        string='Task',
        required=True,
        ondelete='cascade',
        index=True
    )

    allowed_employee_ids = fields.Many2many(
        'hr.employee',
        string='Allowed Employees',
        compute='_compute_allowed_employee_ids'
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        domain="[('id', 'in', allowed_employee_ids)]"
    )

    work_date = fields.Date(
        string='Work Date'
    )

    start_time = fields.Float(
        string='Start Time'
    )

    end_time = fields.Float(
        string='End Time'
    )

    duration = fields.Float(
        string='Duration',
        compute='_compute_duration',
        store=True
    )

    timesheet_line_id = fields.Many2one(
        'account.analytic.line',
        string='Actual Timesheet',
        readonly=True,
        copy=False
    )

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('done', 'Timesheet Created'),
        ],
        string='Status',
        default='draft',
        readonly=True,
        copy=False
    )

    @api.depends(
        'employee_id',
        'employee_id.name',
        'task_id',
        'task_id.name',
        'work_date',
    )
    def _compute_generate_name(self):
        for record in self:
            if not record.employee_id or not record.task_id:
                record.name = False
                continue

            domain = [
                ('employee_id', '=', record.employee_id.id),
                ('task_id', '=', record.task_id.id),
                ('work_date', '!=', False),
            ]

            slots = self.search(domain, order='work_date, start_time, id')

            day_number = 1

            for slot in slots:
                if slot.id == record.id:
                    break
                day_number += 1

            record.name = '%s : %s Day %s' % (
                record.employee_id.name,
                record.task_id.name,
                day_number,
            )

    @api.depends('task_id', 'task_id.user_ids')
    def _compute_allowed_employee_ids(self):
        for record in self:
            users = record.task_id.user_ids

            employees = self.env['hr.employee'].search([
                ('user_id', 'in', users.ids)
            ])

            record.allowed_employee_ids = employees

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            if record.end_time > record.start_time:
                record.duration = round(
                    record.end_time - record.start_time, 2
                )
            else:
                record.duration = 0.0

    @api.constrains('start_time', 'end_time')
    def _check_time(self):
        for record in self:
            if not (0 <= record.start_time < 24):
                raise ValidationError(
                    _('Start Time must be between 00:00 and 24:00.')
                )

            if not (0 <= record.end_time < 24):
                raise ValidationError(
                    _('End Time must be between 00:00 and 24:00.')
                )

            if record.end_time <= record.start_time:
                raise ValidationError(
                    _('End Time must be greater than Start Time.')
                )

    @api.constrains('employee_id', 'task_id')
    def _check_employee_assignment(self):
        for record in self:
            if (
                record.employee_id
                and record.employee_id.user_id not in record.task_id.user_ids
            ):
                raise ValidationError(
                    _('Employee must be assigned to the selected task.')
                )

    def action_create_timesheet(self):
        for record in self:

            if record.state == 'done':
                raise UserError(
                    _('Timesheet has already been created.')
                )

            if not record.employee_id:
                raise UserError(
                    _('Please select an Employee.')
                )

            if not record.work_date:
                raise UserError(
                    _('Please input Work Date.')
                )

            if record.duration <= 0:
                raise UserError(
                    _('Please input valid Start Time and End Time.')
                )

            task = record.task_id

            if not task.project_id:
                raise UserError(
                    _('Task must belong to a Project.')
                )

            # Check employee assignment
            if record.employee_id.user_id not in task.user_ids:
                raise UserError(
                    _('Employee must be assigned to the selected task.')
                )

            # Get Analytic Account
            analytic_account = task.project_id.account_id

            if not analytic_account:
                raise UserError(
                    _(
                        'Please configure an Analytic Account '
                        'on the Project.'
                    )
                )

            # Create native Odoo Timesheet
            timesheet = self.env['account.analytic.line'].create({
                'name': record.name,
                'date': record.work_date,
                'employee_id': record.employee_id.id,
                'project_id': task.project_id.id,
                'task_id': task.id,
                'account_id': analytic_account.id,
                'unit_amount': record.duration,
            })

            record.write({
                'timesheet_line_id': timesheet.id,
                'state': 'done',
            })

        return True
