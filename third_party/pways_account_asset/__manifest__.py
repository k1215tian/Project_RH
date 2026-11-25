# -*- coding: utf-8 -*-
{
    'name': 'Assets Management',
    'version': '18.0.0.0',
    'category': 'Account',
    'depends': ['account'],
    'summary': """Assets Management is an Odoo app for accounting workflows, integrated with Accounting. Search also with similar names such as the related app titles below.

Fixed Assets Management
Asset Management System
Accounting Assets Software
Company Asset Tracking
Assets Management App
Fixed Asset Accounting
Asset Register System
Asset Depreciation Software
Company Assets Tracker
Asset Lifecycle Management""",
    'description': '''
This app allows users to manage accounting assets and depreciation into Odoo. Your user can configure asset types/categories. Depreciation will be computed as per settings and journal entries for depreciation.

Key features:
* Create an asset from accounting.
* Allow you to compute depreciation of assets for periods as configured.
* Account asset types menu for setting up types of assets.
* The system adds assets list view and form views.
* View assets analytic report with depreciation date & vendor.
* View Bar Chart, Line Chart, and Pie Chart for assets analytic report.
* Use the Compute Asset wizard.
* Use the Modify Asset wizard.
* Track computation method (linear, degressive).
* Track computation method (draft, running, close, linear, degressive).
* Extend customer and vendor invoices with module-specific fields.
* Application menus cover Assets, Assets and Revenues, and Generate Assets Entries.
* Launch Asset Types from dedicated window actions.
* Launch Assets Analysis from dedicated window actions.
''',
    'author': 'Preciseways',
    'website': 'http://www.preciseways.com',
    'category': 'Accounting',

    'price': 0.0,
    'currency': "EUR",
    'data': [
        'security/ir.model.access.csv',
        'security/account_asset_security.xml',
        'wizard/asset_depreciation_confirmation_wizard_views.xml',
        'wizard/asset_modify_views.xml',
        'views/account_asset_views.xml',
        'views/account_invoice_views.xml',
        'views/product_views.xml',
        'report/account_asset_report_views.xml',
        'data/account_asset_data.xml',
    ],
 
    'license': 'OPL-1',
    'images': ['static/description/banner.gif'],
}
