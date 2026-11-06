{
    'name': 'API Usage Management',
    'version': '1.0.0',
    'category': 'Technical',
    'summary': 'Manage API configurations and usage quotas',
    'description': """
        API Usage Management
        ====================
        - API Configuration Management
        - API Usage Monitoring
        - Automatic Quota Management
        - API Usage Logging
        - Multi Company Support
    """,
    'depends': [
        'base',
        'mail',
    ],
    "data": [
        "data/ir_cron_data.xml",
        "data/ir_sequence_data.xml",
        "security/ir.model.access.csv",
        "views/api_quota_reset_log_views.xml",
        "views/api_usage_log_views.xml",
        "views/api_usage_menu.xml",
        "views/api_webhook_handler_views.xml",
        "views/setting_api_conf_views.xml",
        "views/templates.xml"
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
