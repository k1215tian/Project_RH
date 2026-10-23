from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MasterMonthly(models.Model):
    _name = "om.master.monthly"
    _description = "Master Monthly Period"
    _order = "year desc, month_number asc"
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

    month = fields.Char(
        string="Month",
        compute="_compute_month",
        required=True,
        readonly=True,
    )

    month_number = fields.Integer(
        string="Month",
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
        string="Closing Date End",
        compute="_compute_closing_date_end",
        store=True,
        readonly=True,
        tracking=True,
    )

    last_accounting_date = fields.Date(
        string="Last Accounting Date",
        compute="_compute_last_accounting_date",
        store=True,
        readonly=True,
        tracking=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        required=True,
        default=1,
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
            "unique_month",
            "unique(company_id, year, month_number)",
            "Monthly period must be unique per year and company.",
        ),
        (
            "unique_code",
            "unique(company_id, code)",
            "Monthly period code must be unique per company.",
        ),
    ]

    @api.depends("month", "year")
    def _compute_display_name(self):
        for record in self:
            if record.month and record.year:
                record.display_name = f"{record.month}{record.year}"
            else:
                record.display_name = False

    @api.depends("month_number")
    def _compute_month(self):
        month_names = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }

        for record in self:
            record.month = month_names.get(record.month_number, False)

    @api.depends("date_end")
    def _compute_closing_date_end(self):
        for record in self:
            record.closing_date_end = (
                record.date_end + timedelta(days=5)
                if record.date_end
                else False
            )

    @api.depends("closing_date_end")
    def _compute_last_accounting_date(self):
        for record in self:
            record.last_accounting_date = record.closing_date_end

    @api.depends("code")
    def _compute_name(self):
        for record in self:
            record.name = record.code or False

    @api.constrains(
        "year",
        "month_number",
        "date_start",
        "date_end",
    )
    def _check_period(self):
        for record in self:
            if not 1 <= record.month_number <= 12:
                raise ValidationError(
                    "Month must be between 1 and 12."
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

            if record.date_start.month != record.month_number:
                raise ValidationError(
                    "Start date does not match month number."
                )

            if record.date_end.month != record.month_number:
                raise ValidationError(
                    "End date does not match month number."
                )

    @api.model
    def generate_year(self, year, company=None):
        """
        Generate monthly periods for a specific calendar year.
        Existing months are skipped; missing months are created.
        """
        company = company or self.env.company

        # Ambil bulan yang sudah tersedia untuk perusahaan dan tahun ini.
        existing_records = self.with_context(
            active_test=False
        ).search([
            ("year", "=", year),
            ("company_id", "=", company.id),
        ])

        existing_months = set(
            existing_records.mapped("month_number")
        )

        periods = []

        for month in range(1, 13):
            # Lewati bulan yang sudah ada.
            if month in existing_months:
                continue

            date_start = fields.Date.to_date(
                f"{year}-{month:02d}-01"
            )

            if month == 12:
                next_month = fields.Date.to_date(
                    f"{year + 1}-01-01"
                )
            else:
                next_month = fields.Date.to_date(
                    f"{year}-{month + 1:02d}-01"
                )

            date_end = next_month - timedelta(days=1)

            periods.append({
                "code": f"{str(year)[-2:]}M{month:02d}",
                "year": year,
                "month_number": month,
                "date_start": date_start,
                "date_end": date_end,
                "sequence": month,
                "company_id": company.id,
            })

        # Buat hanya bulan yang belum tersedia.
        if periods:
            self.create(periods)

        return self.with_context(active_test=False).search([
            ("year", "=", year),
            ("company_id", "=", company.id),
        ], order="month_number asc")

    @api.model
    def _cron_update_period_states(self):
        """
        Cron job harian untuk memperbarui status periode:
        1. Periode belum dimulai -> active = False.
        2. Periode berjalan -> state = 'open', active = True.
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
