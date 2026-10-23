from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class Master3M(models.Model):
    _name = "om.master.3m"
    _description = "Master 3 Months Period"
    _order = "year desc, sequence asc"
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
    )

    sequence = fields.Integer(
        string="Sequence",
        required=True,
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
        inverse="_inverse_val",
    )

    last_accounting_date = fields.Date(
        string="Last Accounting Date",
        compute="_compute_last_accounting_date",
        store=True,
        readonly=True,
        tracking=True,
        inverse="_inverse_val",
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
            "unique_3m",
            "unique(company_id, year, sequence)",
            "3M period must be unique per year and company.",
        ),
        (
            "unique_code",
            "unique(company_id, code)",
            "3M period code must be unique per company.",
        ),
    ]

    def _inverse_val(self):
        for record in self:
            pass

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
        "sequence",
        "date_start",
        "date_end",
    )
    def _check_period(self):
        for record in self:
            if not 1 <= record.sequence <= 4:
                raise ValidationError(
                    "3M sequence must be between 1 and 4."
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

            expected_start_month = (
                (record.sequence - 1) * 3
            ) + 1

            expected_end_month = (
                expected_start_month + 2
            )

            if record.date_start.month != expected_start_month:
                raise ValidationError(
                    "Start date does not match the 3M sequence."
                )

            if record.date_end.month != expected_end_month:
                raise ValidationError(
                    "End date does not match the 3M sequence."
                )

    @api.model
    def generate_year(self, year, company=None):
        """
        Generate four 3-month periods for a specific calendar year.
        Existing sequences are skipped; missing sequences are created.

        Sequence 1 = January - March
        Sequence 2 = April - June
        Sequence 3 = July - September
        Sequence 4 = October - December
        """
        company = company or self.env.company

        existing_records = self.with_context(
            active_test=False
        ).search([
            ("year", "=", year),
            ("company_id", "=", company.id),
        ])

        existing_sequences = set(
            existing_records.mapped("sequence")
        )

        periods = []

        for sequence in range(1, 5):
            # Lewati periode yang sudah ada.
            if sequence in existing_sequences:
                continue

            start_month = ((sequence - 1) * 3) + 1
            end_month = start_month + 2

            date_start = fields.Date.to_date(
                f"{year}-{start_month:02d}-01"
            )

            if end_month == 12:
                next_month = fields.Date.to_date(
                    f"{year + 1}-01-01"
                )
            else:
                next_month = fields.Date.to_date(
                    f"{year}-{end_month + 1:02d}-01"
                )

            date_end = next_month - timedelta(days=1)

            periods.append({
                "code": f"{str(year)[-2:]}Q{sequence}",
                "year": year,
                "sequence": sequence,
                "date_start": date_start,
                "date_end": date_end,
                "company_id": company.id,
            })

        # Buat hanya periode yang belum tersedia.
        if periods:
            self.create(periods)

        return self.with_context(active_test=False).search([
            ("year", "=", year),
            ("company_id", "=", company.id),
        ], order="sequence asc")

    @api.model
    def _cron_update_period_states(self):
        """
        Cron job harian untuk otomatisasi status Quarterly:
        1. Periode belum dimulai -> active = False.
        2. Periode berjalan -> state = 'open', active = True.
        3. Periode sudah lewat -> state = 'closed', active = False.
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
