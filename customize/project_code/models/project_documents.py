# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProjectDocuments(models.Model):
    _name = 'project.documents'
    _description = 'Project Documents'

    name = fields.Char('Name')
    type = fields.Selection([
        ('contract', 'Contract'),
        ('po', 'Purchase Order'),
        ('bast', 'BAST'),
        ('report', 'Report Project'),
        ('sheet', 'Project Sheet'),
        ('attende', 'Attendee Project'),
        ('certificate', 'Certificate Project'),
        ('others', 'Others Doc')],
        string='Type Document')

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    project_member_ids = fields.Many2many(
        related='project_id.member_ids',
        string="Project Members",
        help="Users who are members of this project.",
    )
    filename = fields.Char(
        string="File Name")
    filebinary = fields.Binary(
        string="File Upload")
    check_contract = fields.Boolean(
        string='Contract',
        tracking=True)
    check_po = fields.Boolean(
        string='PO',
        tracking=True)
    upload_date = fields.Date(
        string='Upload Date',
        default=fields.Date.context_today,
        tracking=True,
    )
    check_bast = fields.Boolean(
        string='BAST',
        tracking=True)
    check_lap = fields.Boolean(
        string='Laporan Project',
        tracking=True)
    check_sheet = fields.Boolean(
        string='Project Sheet',
        tracking=True)
    check_absensi = fields.Boolean(
        string='Absensi',
        tracking=True)
    check_sertifikat = fields.Boolean(
        string='Sertifikat',
        tracking=True)
    titleothers = fields.Char(
        string="Document Others")
    check_others = fields.Boolean(
        string='Others',
        tracking=True)
    uploaded_by = fields.Many2one(
        'res.users',
        string='Uploaded By',
        default=lambda self: self.env.user,
        readonly=True,
    )
    notes = fields.Text(
        string='Notes'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('uploaded', 'Uploaded'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ], string='Status',
        default='draft',
        tracking=True)

    verified_by = fields.Many2one(
        'res.users',
        string='Verified By',
        domain=[('id', 'in', project_member_ids)],
        readonly=True,
    )
    verified_date = fields.Datetime(
        string='Verified Date',
        readonly=True,
    )
    active = fields.Boolean(
        'Active',
        default=True,
        help="Set false to hide this document without removing it.")

    def action_upload(self):
        for rec in self:
            if not rec.filebinary:
                raise ValidationError(
                    _("Silakan unggah file terlebih dahulu sebelum mengubah status menjadi Uploaded."))
            rec.state = 'uploaded'

    def action_verify(self):
        for rec in self:
            rec.state = 'verified'
            rec.verified_by = self.env.user.id
            rec.verified_date = fields.Datetime.now()

    def action_reject(self):
        for rec in self:
            rec.state = 'rejected'

    def action_set_to_draft(self):
        for rec in self:
            rec.state = 'draft'
            rec.verified_by = False
            rec.verified_date = False
