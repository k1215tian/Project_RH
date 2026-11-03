# -*- coding: utf-8 -*-
{
    'name': "Auto Replenishment",
    'summary': "Module for auto replenishment between internal warehouses",

    'description': """
        Module for auto replenishment between internal warehouses. 
        Allows you to automatically move products from one warehouse to another when necessary""",

    'author': "odoo-experte",
    'website': "odoo-experte.com",
    "category": "Inventory/Inventory",
    'version': '1.0',
    'license': 'OPL-1',
    'price': 0,
    'currency': 'EUR',
    'support': 'info@odoo-experte.com',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/auto_replenishment_views.xml',
        'views/stock_picking_type_views.xml',
    ],
    'application': True,
    'installable': True,
    'images': ['static/description/banner.png'],
}
