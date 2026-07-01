# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    lob_ids = fields.Many2many(
        'res.partner.lob',
        'partner_lob_rel',
        string="Line of Business (LOB)",
        help="Spesifikasi Line of Business untuk customer ini.")
