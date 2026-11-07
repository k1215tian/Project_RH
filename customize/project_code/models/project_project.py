# -*- coding: utf-8 -*-
import logging

from odoo import _, models, fields, api, Command
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProjectProject(models.Model):
    _inherit = 'project.project'

    project_type_id = fields.Many2one(
        string="Project Type",
        comodel_name='project.type', tracking=True)
    code = fields.Char(string="Project Code")
    description = fields.Text(string="Description")
    user_id = fields.Many2one(
        'res.users', string='Project Manager',
        default=lambda self: self.env.user, tracking=True)
    project_lead_id = fields.Many2one(
        'res.users',
        string="Project Leader")

    # ----------------------------------------------------------------
    # If using hr.employee instead of res.users:
    # - Add 'hr' as a module dependency in __manifest__.py.
    # - Apply a domain to ensure only employees linked to an Odoo user
    #   account can be selected.
    # - Optionally, add additional domain conditions to restrict the
    #   selection to employees eligible to manage the project.
    # ----------------------------------------------------------------

    # project_lead_id = fields.Many2one(
    #     comodel_name='hr.employee',
    #     string="Project Leader",
    #     domain="[('user_id', '!=', False)]"
    # )

    privacy_visibility = fields.Selection([
        ('followers', 'Invited internal users (private)'),
        ('employees', 'All internal users'),
        ('portal', 'Invited portal users and all internal users (public)'),
    ],
        string='followers', required=True,
        default='followers',
        tracking=True,
        help="People to whom this project and its tasks will be visible.\n\n"
        "- Invited internal users: when following a project, internal users will get access to all of its tasks without distinction. "
        "Otherwise, they will only get access to the specific tasks they are following.\n "
        "A user with the project > administrator access right level can still access this project and its tasks, even if they are not explicitly part of the followers.\n\n"
        "- All internal users: all internal users can access the project and all of its tasks without distinction.\n\n"
        "- Invited portal users and all internal users: all internal users can access the project and all of its tasks without distinction.\n"
        "When following a project, portal users will only get access to the specific tasks they are following.\n\n"
        "When a project is shared in read-only, the portal user is redirected to their portal. They can view the tasks they are following, but not edit them.\n"
        "When a project is shared in edit, the portal user is redirected to the kanban and list views of the tasks. They can modify a selected number of fields on the tasks.\n\n"
        "In any case, an internal user with no project access rights can still access a task, "
        "provided that they are given the corresponding URL (and that they are part of the followers if the project is private).")
    project_link = fields.Char(
        string="Project Link")

    @api.depends('account_id.company_id', 'partner_id.company_id')
    def _compute_company_id(self):
        for project in self:
            # if a new restriction is put on the account or the customer, the restriction on the project is updated.
            if project.account_id.company_id:
                project.company_id = project.account_id.company_id
            if not project.company_id and project.partner_id.company_id:
                project.company_id = project.partner_id.company_id

    @api.depends_context('company')
    @api.depends('company_id')
    def _compute_currency_id(self):
        default_currency_id = self.env.company.currency_id
        for project in self:
            project.currency_id = project.company_id.currency_id or default_currency_id

    company_id = fields.Many2one('res.company', string='Company', compute="_compute_company_id",
                                 inverse="_inverse_company_id", store=True, readonly=False)
    currency_id = fields.Many2one('res.currency', compute="_compute_currency_id",
                                  string="Currency", readonly=True, export_string_translation=False)
    contract_value = fields.Monetary(
        string="Contract Value",
        currency_field="currency_id",
    )
    validator_ids = fields.Many2many(
        'hr.employee',
        'project_validator_rel',
        'project_id',
        'employee_id',
        domain="[('user_id','!=', False), ('user_id', 'in', member_ids)]",
        string='Validator')
    approval_ids = fields.Many2many(
        'hr.employee',
        'project_approver_rel',
        'project_id',
        'employee_id',
        domain="[('user_id','!=', False), ('user_id', 'in', member_ids)]",
        string='Approver')

    account_manager_id = fields.Many2one('res.users', string="CRO")
    background = fields.Text(string='Reason Project',)
    expected_result = fields.Text(string='Expected Result Project')
    current_issue = fields.Text(string='Current Issue')
    notes = fields.Text(
        string='Notes / Remarks Project',)
    doc_language = fields.Selection([('indonesia', 'Indonesia'),
                                    ('english', 'English')],
                                    string='Proposal Language',)

    # ----------------------------------------------------------------
    # If using hr.employee instead of res.users:
    # - Add 'hr' as a module dependency in __manifest__.py.
    # - Apply a domain to ensure only employees linked to an Odoo user
    #   account can be selected.
    # - Optionally, add additional domain conditions to restrict the
    #   selection to employees eligible to manage the project.
    # ----------------------------------------------------------------

    # account_manager_id = fields.Many2one(
    #     comodel_name='hr.employee',
    #     string="CRO",
    #     domain="[('user_id', '!=', False)]"
    # )

    document_ids = fields.One2many(
        'project.documents',
        'project_id',
        string='Documents'
    )
    spect_project = fields.Selection([
        ('software', 'Software Development'),
        ('hardware', 'Hardware & Infrastructure'),
        ('services', 'Managed Services'),
        ('consulting', 'Consulting'),
        ('maintenance', 'Maintenance & Support'),
        ('others', 'Others')
    ],
        string="Spect Project",
        help="Spesifikasi type project.")
    document_count = fields.Integer(
        string='Document Count',
        compute='_compute_document_count'
    )

    member_ids = fields.Many2many(
        comodel_name="res.users",
        relation="project_project_user_rel",
        column1="project_id",
        column2="user_id",
        string="Project Members",
        help="Users who are members of this project.",
    )

    team_id = fields.Many2one(
        comodel_name="crm.team",
        string="Project Team",
        domain=[("team_type", "=", "project")],
    )

    move_ids = fields.Many2one(
        comodel_name="stock.move",
        string="Product COGS",
        help="List of stock moves related to this project.",
        ondelete="cascade",
    )

    @api.onchange("team_id")
    def _onchange_team_id(self):
        if self.team_id:
            self.member_ids = [Command.set(self.team_id.team_member_ids.ids)]
        else:
            self.member_ids = [Command.clear()]

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)

        for project in projects:
            if project.member_ids:
                project._sync_project_followers(
                    old_members=self.env["res.users"],
                    new_members=project.member_ids,
                    send_notification=False,
                )

        return projects

    def write(self, vals):
        if "member_ids" not in vals:
            return super().write(vals)
        old_members_map = {project.id: project.member_ids for project in self}

        result = super().write(vals)

        for project in self:
            project._sync_project_followers(
                old_members=old_members_map.get(
                    project.id, self.env["res.users"]),
                new_members=project.member_ids,
                send_notification=True,
            )

        return result

    def _sync_project_followers(self, old_members, new_members, send_notification=True):
        """Synchronize project members with chatter followers."""
        self.ensure_one()
        removed_members = old_members - new_members
        added_members = new_members - old_members
        if removed_members:
            self.message_unsubscribe(
                partner_ids=removed_members.partner_id.ids)

        if added_members:
            self.message_subscribe(partner_ids=added_members.partner_id.ids)

            if send_notification:
                self._send_member_invitation_email(added_members)

    def _send_member_invitation_email(self, members):
        """Send notification email to newly added members."""
        self.ensure_one()

        template = self.env.ref(
            "project_team.project_new_member", raise_if_not_found=False)
        if not template:
            return
        valid_members = members.filtered(lambda u: u.partner_id.email)

        for member in valid_members:
            template.with_context(member=member.partner_id.name).send_mail(
                self.id,
                force_send=True,
                email_values={
                    "email_to": member.partner_id.email,
                    "subject": _("Invitation to follow Project: %s") % self.display_name,
                },
            )

    def _compute_document_count(self):
        for project in self:
            project.document_count = self.env['project.documents'].search_count([
                ('project_id', '=', project.id)
            ])

    def action_open_documents(self):
        self.ensure_one()
        return {
            'name': _('Project Documents'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.documents',
            'view_mode': 'tree,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }
