# -*- coding: utf-8 -*-
{
    'name': "Project Code",
    'summary': "Solusi efisien untuk manajemen alur kerja dan pelacakan progres proyek secara real-time.",

    'description': """
        Modul Project Code membantu organisasi dalam mengelola siklus hidup proyek 
        secara komprehensif. Fitur utama mencakup:
        
        *   Manajemen tugas yang intuitif dan terintegrasi.
        *   Pelaporan progres otomatis untuk setiap fase proyek.
        *   Kolaborasi tim yang ditingkatkan melalui dasbor terpusat.
        *   Analisis data untuk pengambilan keputusan yang lebih cepat.
        
        Modul ini dirancang khusus untuk Odoo 18 dengan memanfaatkan performa 
        framework terbaru untuk memberikan pengalaman pengguna yang responsif.
    """,

    'author': "Kristian Maulana",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Operations/Project',
    'version': '0.1',
    "license": "AGPL-3",

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'project',
        'account',
        'project_teams',
        'project_stock',
        'project_stock_account',
        'stock'
    ],
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
    'installable': True,
    'application': True,
    'auto_install': False,
}
