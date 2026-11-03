# -*- coding: utf-8 -*-
from odoo import models, fields, _


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    auto_replenishment = fields.Boolean()
    auto_replenishment_line_ids = fields.One2many('auto.replenishment.line', 'picking_type_id')

    def action_internal_auto_replenishment(self):
        """Run all scheduled replenishments"""
        return self.search([
            ('code', '=', 'internal'),
            ('auto_replenishment', '=', True)
        ]).action_auto_replenish()

    def action_auto_replenish(self):
        today = fields.Date.today()
        for rec in self:
            replenishment_lines = rec.auto_replenishment_line_ids
            lines_to_replenish = self.env['auto.replenishment.line']
            for line in replenishment_lines:
                if (
                    line.period_tag_ids and
                    all(p.date_start and today < p.date_start or
                        p.date_stop and today > p.date_stop
                        for p in line.period_tag_ids)
                ):
                    continue
                if line.qty_to_replenish:
                    lines_to_replenish |= line
            if lines_to_replenish:
                picking_vals = {
                    'picking_type_id': rec.id,
                    'partner_id': self.env.user.partner_id.id,  # odoo-bot
                    'origin': _('internal auto replenishment'),
                    'location_dest_id': rec.default_location_dest_id.id,
                    'location_id': rec.default_location_src_id.id,
                    'move_type': 'direct'
                }
                picking = self.env['stock.picking'].create(picking_vals)
                moves = lines_to_replenish._create_stock_moves(picking)
                picking.action_confirm()
                picking.action_assign()
