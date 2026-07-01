# -*- coding: utf-8 -*-
{
    'name': "project_code",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',
    "license": "AGPL-3",

    # any module necessary for this one to work correctly
    'depends': ['base', 'crm', 'project', 'account'],
    # always loaded
    'data': [
        "data/res_partner_lob.xml",
        "security/ir.model.access.csv",
        "views/project_documents_views.xml",
        "views/project_project_views.xml",
        "views/project_task_views.xml",
        "views/project_type_views.xml",
        "views/res_partner_lob_views.xml",
        "views/res_partner_views.xml",
        "views/task_module_views.xml",
        'views/menus_views.xml'
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}
