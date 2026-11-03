# -*- coding: utf-8 -*-
# from odoo import http


# class ScheduleReporting(http.Controller):
#     @http.route('/schedule_reporting/schedule_reporting', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/schedule_reporting/schedule_reporting/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('schedule_reporting.listing', {
#             'root': '/schedule_reporting/schedule_reporting',
#             'objects': http.request.env['schedule_reporting.schedule_reporting'].search([]),
#         })

#     @http.route('/schedule_reporting/schedule_reporting/objects/<model("schedule_reporting.schedule_reporting"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('schedule_reporting.object', {
#             'object': obj
#         })

