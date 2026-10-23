# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResPartnerLob(models.Model):
    _name = 'res.partner.lob'
    _description = 'Partner Line of Business'
    _order = 'code'

    name = fields.Char('Name')
    code = fields.Char('Code')
    islock = fields.Boolean('Lock')
    color = fields.Integer(
        string='Color Index',
        export_string_translation=False)
    # ---------------------------------------------------------
    # 1. SQL CONSTRAINTS
    # ---------------------------------------------------------
    _sql_constraints = [
        # Format: ('nama_constraint', 'definisi_sql', 'Pesan Error')
        ('code_unique', 'UNIQUE(code)',
         'Kode Line of Business sudah digunakan. Kode harus unik!')
    ]

    # ---------------------------------------------------------
    # 2. PYTHON CONSTRAINTS
    # ---------------------------------------------------------
    @api.constrains('code')
    def _check_code_format(self):
        for record in self:
            # Contoh validasi: Kode tidak boleh mengandung spasi
            if record.code and ' ' in record.code:
                raise ValidationError(
                    'Kode Line of Business tidak boleh mengandung spasi.')

            # Anda juga bisa menambahkan validasi lain di sini jika butuh
            # if not record.code.isalnum():
            #     raise ValidationError('Kode hanya boleh berisi huruf dan angka.')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for record in self:
            # Pengecekan dilakukan untuk menghindari error 'FalseType' jika field kosong
            formatted_name = record.name.title() if record.name else ""
            formatted_code = record.code.upper() if record.code else ""

            # Menggabungkan code dan name (Format standar Odoo biasanya menggunakan kurung siku untuk kode)
            if formatted_code and formatted_name:
                record.display_name = f"[{formatted_code}] {formatted_name}"
            elif formatted_name:
                record.display_name = formatted_name
            elif formatted_code:
                record.display_name = f"[{formatted_code}]"
            else:
                record.display_name = False
