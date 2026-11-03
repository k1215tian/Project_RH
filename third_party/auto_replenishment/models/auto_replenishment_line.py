# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api
from odoo.tools import frozendict


class AutoReplenishmentLine(models.Model):
    _name = 'auto.replenishment.line'
    _description = 'Auto Replenishment'

    picking_type_id = fields.Many2one('stock.picking.type')
    product_id = fields.Many2one('product.product', ondelete='cascade', required=True, check_company=True)
    period_tag_ids = fields.Many2many(
        'auto.replenishment.period.tag',
        'auto_replenishment_line_period_tag_rel',
        'line_id',
        'period_tag_id',
        'Periods'
    )
    product_uom = fields.Many2one('uom.uom', 'Unit of Measure', related='product_id.uom_id')
    qty_min = fields.Float('Min', required=True, default=0.0)
    qty_on_hand = fields.Float('On Hand', readonly=True, compute='_compute_qty')
    qty_forecast = fields.Float('Forecast', readonly=True, compute='_compute_qty')
    qty_to_replenish = fields.Float('To Replenish', readonly=True, compute='_compute_qty_to_replenish')

    @api.depends('product_id', 'picking_type_id.default_location_dest_id',
                 'product_id.stock_move_ids', 'product_id.stock_move_ids.state',
                 'product_id.stock_move_ids.date', 'product_id.stock_move_ids.product_uom_qty')
    def _compute_qty(self):
        lines_contexts = defaultdict(lambda: self.env['auto.replenishment.line'])
        for line in self:
            if not line.product_id:
                line.qty_on_hand = False
                line.qty_forecast = False
                continue
            line_context = line._get_product_context()
            product_context = frozendict({**line_context})
            lines_contexts[product_context] |= line
        for line_context, lines_by_context in lines_contexts.items():
            products_qty = {
                p['id']: p for p in lines_by_context.product_id.with_context(line_context).read(['qty_available', 'virtual_available'])
            }
            for line in lines_by_context:
                line.qty_on_hand = products_qty[line.product_id.id]['qty_available']
                line.qty_forecast = products_qty[line.product_id.id]['virtual_available']

    @api.depends('qty_forecast', 'qty_min')
    def _compute_qty_to_replenish(self):
        """Replenish to minimum qty (for now)"""
        for line in self:
            if not line.product_id:
                line.qty_to_replenish = False
                continue
            to_replenish = line.qty_min - line.qty_forecast
            line.qty_to_replenish = to_replenish if to_replenish > 0.0 else 0.0

    def _get_product_context(self, visibility_days=0):
        self.ensure_one()
        return {
            'location': self.picking_type_id.default_location_dest_id.id,
        }

    def _create_stock_moves(self, picking):
        moves = self.env['stock.move']
        for line in self:
            moves += self.env['stock.move'].create(
                line._get_stock_move_values(picking)
            )
        return moves

    def _get_stock_move_values(self, picking):
        self.ensure_one()
        return {
            'name': '',
            'product_id': self.product_id.id,
            'product_uom': self.product_uom.id,
            'product_uom_qty': self.qty_to_replenish,
            'location_id': picking.picking_type_id.default_location_src_id.id,
            'location_dest_id': picking.picking_type_id.default_location_dest_id.id,
            'picking_id': picking.id,
            'state': 'draft',
            'picking_type_id': picking.picking_type_id.id,
            'warehouse_id': picking.picking_type_id.warehouse_id.id,
        }
