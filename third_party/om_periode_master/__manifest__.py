{
    "name": "OM Master Periode",
    "version": "18.0.1.0.0",
    "category": "Operations",
    "summary": "General master period management",
    "description": """
        OM Master Periode
        =================

        General period management inspired by Odoo Fiscal Years.

        Supported period types:
        - Yearly
        - Quarterly
        - Monthly
        - Weekly

        Features:
        - Automatic period generation
        - Calendar year management
        - Weekly period management
        - Monthly period management
        - Quarterly period management
        - Yearly period management
        - Period hierarchy
        - Period state management
        - Period overlap validation
        - Period closing
        - Multi-company support
    """,
    "author": "Kristian Maulana",
    "website": False,
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail"
    ],

    "data": [
        "data/ir_cron.xml",
        "security/ir.model.access.csv",
        "views/ir_cron_views.xml",
        "views/main_menu.xml",
        "views/om_master_3m_views.xml",
        "views/om_master_monthly_views.xml",
        "views/om_master_weekly_views.xml",
        "views/res_company_views.xml"
    ],

    "demo": [
    ],
    "icon": "static/description/icon.png",
    "installable": True,
    "application": True,
    "auto_install": False,
}
