# -*- coding: utf-8 -*-
from random import randint

from odoo import models, fields


class AutoReplenishmentPeriodTag(models.Model):
    _name = 'auto.replenishment.period.tag'
    _description = 'Auto Replenishment Period Tag'

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char(required=True)
    date_start = fields.Date()
    date_stop = fields.Date()
    color = fields.Integer('Color Index', default=_get_default_color)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Replenishment Period name already exists!"),
    ]
