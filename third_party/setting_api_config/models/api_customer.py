
from dateutil.relativedelta import relativedelta

import logging
import re

from odoo import SUPERUSER_ID, models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class ApiCustomer(models.Model):
    _name = 'api.customer'
    _description = 'API Customer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ---------------------------------------------------------
    # BASIC INFORMATION
    # ---------------------------------------------------------

    name = fields.Char(
        string='Customer Name',
        required=True,
        tracking=True,
    )

    code = fields.Char(
        string='Customer Code',
        required=True,
        copy=False,
        index=True,
        tracking=True,
    )

    description = fields.Text(
        string='Description',
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    user_id = fields.Many2one(
        'res.users',
        string='API Execution User',
        required=True,
        help='Odoo user used to execute inbound API business operations.',
    )

    credential_ids = fields.One2many(
        'api.credential',
        'customer_id',
        string='API Credentials',
    )

    credential_count = fields.Integer(
        string='Credential Count',
        compute='_compute_credential_count',
    )

    endpoint_ids = fields.Many2many(
        'api.endpoint',
        'api_customer_endpoint_rel',
        'customer_id',
        'endpoint_id',
        string='Allowed API Endpoints',
    )

    quota_period = fields.Selection([
        ('daily', 'Daily'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ],
        string='Quota Period',
        default='monthly',
        required=True,
        tracking=True,
    )

    included_quota_units = fields.Integer(
        string='Included Quota Units',
        default=10000,
        required=True,
        tracking=True,
    )

    used_units = fields.Integer(
        string='Used Units',
        default=0,
        readonly=True,
        tracking=True,
    )

    remaining_units = fields.Integer(
        string='Remaining Units',
        compute='_compute_remaining_units',
    )

    allow_overage = fields.Boolean(
        string='Allow Overage',
        default=False,
        tracking=True,
        help='Allow API usage beyond included quota.',
    )

    unit_price = fields.Monetary(
        string='Price Per Unit',
        currency_field='currency_id',
        default=0.0,
        tracking=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )

    period_start = fields.Date(
        string='Period Start',
        readonly=True,
        copy=False,
    )

    period_end = fields.Date(
        string='Period End',
        readonly=True,
        copy=False,
    )

    usage_log_ids = fields.One2many(
        'api.usage.log',
        'customer_id',
        string='API Usage Logs',
    )

    total_requests = fields.Integer(
        string='Total Requests',
        compute='_compute_usage_statistics',
    )

    total_success_requests = fields.Integer(
        string='Successful Requests',
        compute='_compute_usage_statistics',
    )

    total_failed_requests = fields.Integer(
        string='Failed Requests',
        compute='_compute_usage_statistics',
    )

    total_usage_units = fields.Integer(
        string='Total Usage Units',
        compute='_compute_usage_statistics',
    )

    total_billable_units = fields.Integer(
        string='Billable Units',
        compute='_compute_usage_statistics',
    )

    total_usage_charge = fields.Monetary(
        string='Total Usage Charge',
        currency_field='currency_id',
        compute='_compute_usage_statistics',
    )

    _sql_constraints = [
        (
            'api_customer_code_unique',
            'unique(code)',
            'Customer code must be unique.',
        ),
        (
            'api_customer_quota_nonnegative',
            'CHECK(included_quota_units >= 0 AND used_units >= 0)',
            'Quota and used units cannot be negative.',
        ),
        (
            'api_customer_price_nonnegative',
            'CHECK(unit_price >= 0)',
            'Unit price cannot be negative.',
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)

        for vals in vals_list:
            quota_period = vals.get('quota_period', 'monthly')
            period_start = vals.get('period_start') or today

            vals.setdefault('period_start', period_start)
            vals.setdefault(
                'period_end',
                self._calculate_period_end(
                    quota_period,
                    period_start,
                ),
            )

        return super().create(vals_list)

    @api.model
    def _calculate_period_end(self, period, start_date):
        start_date = fields.Date.to_date(start_date)

        if period == 'daily':
            return start_date + relativedelta(days=1)

        if period == 'yearly':
            return start_date + relativedelta(years=1)

        return start_date + relativedelta(months=1)

    @api.depends('credential_ids')
    def _compute_credential_count(self):
        for customer in self:
            customer.credential_count = len(customer.credential_ids)

    @api.depends('included_quota_units', 'used_units')
    def _compute_remaining_units(self):
        for customer in self:
            customer.remaining_units = max(
                0,
                customer.included_quota_units - customer.used_units,
            )

    @api.depends(
        'usage_log_ids.state',
        'usage_log_ids.usage_units',
        'usage_log_ids.billable_units',
        'usage_log_ids.usage_charge',
    )
    def _compute_usage_statistics(self):
        """Aggregate in SQL instead of loading every log into memory."""

        stats = {}

        if self.ids:
            groups = self.env['api.usage.log']._read_group(
                [('customer_id', 'in', self.ids)],
                ['customer_id', 'state'],
                [
                    '__count',
                    'usage_units:sum',
                    'billable_units:sum',
                    'usage_charge:sum',
                ],
            )

            for customer, state, count, units, billable, charge in groups:
                data = stats.setdefault(customer.id, {
                    'total': 0, 'success': 0, 'failed': 0,
                    'units': 0, 'billable': 0, 'charge': 0.0,
                })
                data['total'] += count
                data['units'] += units or 0
                data['billable'] += billable or 0
                data['charge'] += charge or 0.0

                if state == 'success':
                    data['success'] += count
                elif state in ('error', 'failed'):
                    data['failed'] += count

        for customer in self:
            data = stats.get(customer.id, {})
            customer.total_requests = data.get('total', 0)
            customer.total_success_requests = data.get('success', 0)
            customer.total_failed_requests = data.get('failed', 0)
            customer.total_usage_units = data.get('units', 0)
            customer.total_billable_units = data.get('billable', 0)
            customer.total_usage_charge = data.get('charge', 0.0)

    @api.constrains('user_id', 'company_id')
    def _check_execution_user_company(self):
        for customer in self:
            if customer.user_id and customer.company_id:
                if customer.company_id not in customer.user_id.company_ids:
                    raise ValidationError(_(
                        'The API execution user must have access '
                        'to the customer company.'
                    ))

    @api.constrains('period_start', 'period_end')
    def _check_period_dates(self):
        for customer in self:
            if (
                customer.period_start
                and customer.period_end
                and customer.period_end <= customer.period_start
            ):
                raise ValidationError(_(
                    'Period end must be later than period start.'
                ))

    @api.constrains('code')
    def _check_code_format(self):
        # The code is embedded in the API key prefix, which is split on "."
        for customer in self:
            if not re.fullmatch(r'[A-Za-z0-9_-]{2,32}', customer.code or ''):
                raise ValidationError(_(
                    'Customer code may only contain letters, digits, '
                    '"_" and "-" (2-32 characters).'
                ))

    def _reserve_units(self, units):
        """
        Atomically reserve API usage units.

        Runs in its OWN cursor and commits immediately, so the customer row
        is not locked for the whole request and the reservation survives a
        rollback of the caller. It also lazily resets an expired period, so
        quota is correct even if the cron has not run yet.

        Returns {'used_units': int, 'billable_units': int}
        Raises UserError when quota is exceeded.
        """

        self.ensure_one()

        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise ValidationError(_('Usage units must be a positive integer.'))

        with self.pool.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env['api.customer'].browse(self.id)._reset_quota()

            cr.execute(SQL("""
                UPDATE api_customer
                   SET used_units = used_units + %s
                 WHERE id = %s
                   AND active = TRUE
                   AND (
                        allow_overage = TRUE
                        OR used_units + %s <= included_quota_units
                   )
             RETURNING used_units, included_quota_units
            """, units, self.id, units))

            result = cr.fetchone()

        if not result:
            raise UserError(_(
                'API quota exceeded or customer is inactive.'
            ))

        new_used_units, quota_units = result

        billable_before = max(0, new_used_units - units - quota_units)
        billable_after = max(0, new_used_units - quota_units)

        self.invalidate_recordset([
            'used_units', 'remaining_units', 'period_start', 'period_end',
        ])

        return {
            'used_units': new_used_units,
            'billable_units': billable_after - billable_before,
        }

    def _refund_units(self, units):
        """
        Refund previously reserved units (own cursor, committed).
        """

        self.ensure_one()

        if not isinstance(units, int) or isinstance(units, bool) or units <= 0:
            raise ValidationError(_('Refund units must be a positive integer.'))

        with self.pool.cursor() as cr:
            cr.execute(SQL("""
                UPDATE api_customer
                   SET used_units = GREATEST(0, used_units - %s)
                 WHERE id = %s
            """, units, self.id))

        self.invalidate_recordset(['used_units', 'remaining_units'])

        return True

    def _reset_quota(self):
        """
        Reset quota when billing period expires.
        """

        self.ensure_one()

        self.env.cr.execute(SQL("""
            SELECT period_start, period_end, quota_period,
                   used_units, included_quota_units
              FROM api_customer
             WHERE id = %s
             FOR UPDATE
        """, self.id))

        result = self.env.cr.fetchone()

        if not result:
            return False

        period_start, period_end, quota_period, old_used, included = result
        today = fields.Date.context_today(self)

        if not period_end or period_end > today:
            return False

        new_start = period_end
        new_end = self._calculate_period_end(quota_period, new_start)

        while new_end <= today:
            new_start = new_end
            new_end = self._calculate_period_end(quota_period, new_start)

        self.write({
            'used_units': 0,
            'period_start': new_start,
            'period_end': new_end,
        })

        # Make sure the ORM write is in the DB before any raw SQL follows.
        self.flush_recordset(['used_units', 'period_start', 'period_end'])

        self.env['api.quota.reset.log'].sudo().create({
            'customer_id': self.id,
            'old_quota': max(0, included - old_used),
            'new_quota': included,
            'reset_type': quota_period,
        })

        return True

    @api.model
    def _cron_reset_quota(self):
        customers = self.search([
            ('active', '=', True),
            ('period_end', '<=', fields.Date.today()),
        ])

        for customer in customers:
            try:
                with self.env.cr.savepoint():
                    customer._reset_quota()
            except Exception:
                _logger.exception(
                    'Failed to reset API quota for customer %s',
                    customer.display_name,
                )

    def action_view_credentials(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('API Credentials'),
            'res_model': 'api.credential',
            'view_mode': 'list,form',
            'domain': [('customer_id', '=', self.id)],
            'context': {
                'default_customer_id': self.id,
            },
        }

    def action_view_usage_logs(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('API Usage Logs'),
            'res_model': 'api.usage.log',
            'view_mode': 'list,form',
            'domain': [('customer_id', '=', self.id)],
            'context': {
                'default_customer_id': self.id,
            },
        }
