{
    'name': 'Custom Fixed Asset Integration',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Integration between Purchase, Inventory, Accounting and Fixed Assets',
    'description': """ 
    Custom Fixed Asset Integration

    This module integrates the fixed asset management process with Purchase, Inventory, Accounting, and Fixed Asset Management.
    Features

    1.    Purchase Management
            Asset identification on Purchase Order Lines.
            Asset category and model selection.
            Purchase Order tracking.
    2.    Inventory Management
            Asset tracking during goods receipt.
            Serial/Lot number integration.
            Physical location management.
            Asset custodian management.
    3.    Accounting Management
            Vendor Bill integration.
            Asset creation upon invoice validation.
            Partial billing and receipt support.
            Asset validation and cancellation controls.
    4.    Fixed Asset Management
            Automatic asset numbering.
            Automatic fixed asset creation.
            Purchase, Receipt, and Vendor Bill references.
            Physical asset metadata.
            Asset audit trail.
            Duplicate asset prevention.
    5.    Security and Audit
            Custom security groups.
            Access rights and record rules.
            Asset transaction history.
    6.    Automated Testing
            Full transaction testing.
            Partial transaction testing.
            Cancellation testing.
            Idempotency testing. """,
    'author': 'Kristian Maulana',
    'website': '',
    'license': 'LGPL-3',
    'depends': [ 
        'base',
        'product',
        'purchase',
        'stock',
        'account',
    #    'account_asset',
    ],
    'data': [
        # Security
        'security/asset_security.xml',
        'security/ir.model.access.csv',

        # Master Data & Sequence
        'data/product_category.xml',
        'data/asset_sequence.xml',

        # Views
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/account_asset_views.xml',
    ],
    'test': [
        'tests/test_asset_integration.py',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,

}