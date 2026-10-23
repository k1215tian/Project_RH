import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def _get_period_timezone_selection(self):
        return [(tz, tz) for tz in pytz.all_timezones]

    period_timezone = fields.Selection(
        selection=_get_period_timezone_selection,
        string="Period Timezone",
        default="Asia/Jakarta",
        required=True,
        help=(
            "Timezone used by Master Periode scheduler "
            "to determine the beginning of a new year."
        ),
    )

    @api.constrains("period_timezone")
    def _check_period_timezone(self):
        valid_timezones = set(pytz.all_timezones)

        for company in self:
            if company.period_timezone not in valid_timezones:
                raise ValidationError(
                    "Invalid timezone: %s" % company.period_timezone
                )
