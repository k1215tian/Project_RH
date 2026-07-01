
from odoo import api, fields, models, Command, _

class CrmTeam(models.Model):
    _inherit = 'crm.team'

    # Mengubah nama field menjadi singular + _ids sesuai standar Odoo untuk relasi
    team_type = fields.Selection(
        selection=[('sale', 'Sale'), ('project', 'Project')],
        string="Type", 
        default="sale"
    )
    code = fields.Char(string="Team Code")

    team_member_ids = fields.Many2many(
        comodel_name='res.users',
        relation='crm_team_project_user_rel',
        column1='team_id',
        column2='user_id',
        string='Project Members',
        help="Project's members are users who can have access to the tasks related to this project."
    )