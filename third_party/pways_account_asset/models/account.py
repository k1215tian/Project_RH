# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    asset_depreciation_ids = fields.One2many('account.asset.depreciation.line', 'move_id', string='Assets Depreciation Lines', ondelete="restrict")

    def _valid_field_parameter(self, field, name):
        return name == 'ondelete' or super()._valid_field_parameter(field, name)

    def button_cancel(self):
        for move in self:
            for line in move.asset_depreciation_ids:
                line.move_posted_check = False
        return super(AccountMove, self).button_cancel()

    def action_post(self, invoice=False):
        for move in self:
            for depreciation_line in move.asset_depreciation_ids:
                depreciation_line.post_lines_and_close_asset()
        return super(AccountMove, self).action_post()
