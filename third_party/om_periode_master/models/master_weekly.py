from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MasterWeekly(models.Model):
    _name = "om.master.weekly"
    _description = "Master Weekly Period"
    _order = "year desc, week_number asc"
    _rec_name = "code"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    name = fields.Char(
        string="Name",
        compute="_compute_name",
        store=True,
        readonly=True,
    )

    code = fields.Char(
        string="Code",
        required=True,
        readonly=True,
        copy=False,
    )

    year = fields.Integer(
        string="Year",
        required=True,
        index=True,
        readonly=True,

    )

    week_number = fields.Integer(
        string="Week",
        required=True,
        readonly=True,
    )

    date_start = fields.Date(
        string="Start Date",
        required=True,
        readonly=True,
    )

    date_end = fields.Date(
        string="End Date",
        required=True,
        readonly=True,
    )

    closing_date_end = fields.Date(
        string="Closing Date",
        required=False,
        track_visibility='onchange'
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("closed", "Closed"),
        ],
        string="Status",
        default="draft",
        required=True,
        track_visibility='onchange'
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        track_visibility='onchange'
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )

    _sql_constraints = [
        (
            "unique_week",
            "unique(company_id, year, week_number)",
            "Weekly period must be unique per year and company.",
        ),
        (
            "unique_code",
            "unique(company_id, code)",
            "Weekly period code must be unique per company.",
        ),
    ]

    @api.depends("code")
    def _compute_name(self):
        for record in self:
            record.name = record.code or False

    @api.constrains(
        "year",
        "week_number",
        "date_start",
        "date_end",
    )
    def _check_period(self):
        for record in self:
            if record.week_number < 1:
                raise ValidationError(
                    "Week number must be greater than zero."
                )

            if record.date_start > record.date_end:
                raise ValidationError(
                    "Start date cannot be greater than end date."
                )

            if record.date_start.year != record.year:
                raise ValidationError(
                    "Start date must belong to the selected year."
                )

            if record.date_end.year != record.year:
                raise ValidationError(
                    "End date must belong to the selected year."
                )

            days = (
                record.date_end - record.date_start
            ).days + 1

            if days > 7:
                raise ValidationError(
                    "Weekly period cannot contain more than 7 days."
                )

    @api.model
    def generate_year(self, year, company=None):
        company = company or self.env.company

        date_start = fields.Date.to_date(f"{year}-01-01")
        date_end = fields.Date.to_date(f"{year}-12-31")

        # Ambil seluruh minggu yang sudah tersedia.
        existing_periods = self.with_context(
            active_test=False
        ).search([
            ("company_id", "=", company.id),
            ("year", "=", year),
        ])

        existing_weeks = set(existing_periods.mapped("week_number"))

        current_start = date_start
        week_number = 1

        while current_start <= date_end:
            current_end = min(
                current_start + timedelta(days=6),
                date_end,
            )

            if week_number not in existing_weeks:
                vals = {
                    "code": f"{str(year)[-2:]}W{week_number:02d}",
                    "year": year,
                    "week_number": week_number,
                    "date_start": current_start,
                    "date_end": current_end,
                    "company_id": company.id,
                }

                try:
                    # Savepoint menjaga transaksi tetap dapat
                    # diproses jika pembuatan record gagal.
                    with self.env.cr.savepoint():
                        self.create(vals)

                except IntegrityError:
                    # Pastikan konflik memang berasal dari
                    # periode minggu yang sudah dibuat.
                    existing = self.with_context(
                        active_test=False
                    ).search([
                        ("company_id", "=", company.id),
                        ("year", "=", year),
                        ("week_number", "=", week_number),
                    ], limit=1)

                    if not existing:
                        raise

            current_start = current_end + timedelta(days=1)
            week_number += 1

        return self.with_context(active_test=False).search([
            ("company_id", "=", company.id),
            ("year", "=", year),
        ], order="week_number asc")

    @api.model
    def _cron_update_period_states(self):
        """
        Cron job harian untuk otomatisasi status weekly:
        1. Periode belum dimulai -> active = False.
        2. Periode sedang berjalan -> state = 'open', active = True.
        3. Periode sudah berakhir -> state = 'closed', active = False.
        """
        today = fields.Date.today()
        Period = self.with_context(active_test=False)

        # 1. Periode yang belum dimulai
        periods_to_deactivate = Period.search([
            ('date_start', '>', today),
            ('active', '=', True),
        ])

        if periods_to_deactivate:
            periods_to_deactivate.sudo().write({
                'active': False,
            })

        # 2. Periode yang sedang berjalan
        periods_to_open = Period.search([
            ('date_start', '<=', today),
            ('date_end', '>=', today),
            '|',
            ('state', '!=', 'open'),
            ('active', '=', False),
        ])

        if periods_to_open:
            periods_to_open.sudo().write({
                'state': 'open',
                'active': True,
            })

        # 3. Periode yang sudah berakhir
        periods_to_close = Period.search([
            ('date_end', '<', today),
            '|',
            ('state', '!=', 'closed'),
            ('active', '=', True),
        ])

        if periods_to_close:
            periods_to_close.sudo().write({
                'state': 'closed',
                'active': False,
            })
