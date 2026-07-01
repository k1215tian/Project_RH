# -*- coding: utf-8 -*-
# from odoo import http


# class ProjectCode(http.Controller):
#     @http.route('/project_code/project_code', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/project_code/project_code/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('project_code.listing', {
#             'root': '/project_code/project_code',
#             'objects': http.request.env['project_code.project_code'].search([]),
#         })

#     @http.route('/project_code/project_code/objects/<model("project_code.project_code"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('project_code.object', {
#             'object': obj
#         })

