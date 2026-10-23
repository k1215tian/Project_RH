from odoo import models, api, fields

class OMMasterPeriodDashboard(models.AbstractModel):
    _name = 'om.period.dashboard'
    _description = 'OM Period Dashboard Aggregator Base'

    @api.model
    def get_dashboard_data(self, year=None):
        if not year:
            year = fields.Date.today().year

        monthly_periods = self.env['om.master.monthly'].search([
            ('year', '=', int(year))
        ], order='date_start asc')

        labels = [p.name or f"M{p.month_number:02d}" for p in monthly_periods]

        return {
            'periods': [{'id': p.id, 'start': p.date_start, 'end': p.date_end} for p in monthly_periods],
            'labels': labels,
            'datasets': {},
            'summary_cards': [],  # Dynamic card configs list
        }
