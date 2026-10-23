from datetime import datetime
from odoo import api, models


class MasterPeriodScheduler(models.Model):
    _name = "om.master.period.scheduler"
    _description = "Master Period Scheduler"

    @api.model
    def cron_generate_periods(self):
        """Generate periode tahun depan (Dijalankan 31 Des)"""
        companies = self.env["res.company"].search([("active", "=", True)])
        next_year = datetime.now().year + 1

        for company in companies:
            self.env["om.master.weekly"].generate_year(
                datetime.now().year, company)
            self.env["om.master.monthly"].generate_year(
                datetime.now().year, company)
            self.env["om.master.3m"].generate_year(
                datetime.now().year, company)
            self.env["om.master.weekly"].generate_year(next_year, company)
            self.env["om.master.monthly"].generate_year(next_year, company)
            self.env["om.master.3m"].generate_year(next_year, company)

    @api.model
    def cron_update_all_period_states(self):
        """
        Dijalankan harian untuk meng-update status & nonaktifkan periode
        Weekly, Monthly, dan 3M secara bersamaan.
        """
        self.env["om.master.weekly"]._cron_update_period_states()
        self.env["om.master.monthly"]._cron_update_period_states()
        self.env["om.master.3m"]._cron_update_period_states()
