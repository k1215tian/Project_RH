import logging
import requests

from urllib.parse import urlparse
from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


_logger = logging.getLogger(__name__)


class SettingApiConf(models.Model):
    _name = 'setting.api.conf'
    _description = 'Setting API Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True
    )

    auth_type = fields.Selection([
        ('api_key', 'API Key'),
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Authentication'),
        ('custom', 'Custom Header'),
        ('none', 'No Authentication'),
    ], string='Authentication Type', default='api_key')

    api_type = fields.Selection([
        ('ai', 'Artificial Intelligence'),
        ('payment', 'Payment Gateway'),
        ('shipping', 'Shipping & Logistics'),
        ('communication', 'Communication'),
        ('storage', 'Cloud Storage'),
        ('social', 'Social Media'),
        ('e-commerce', 'E-Commerce'),
        ('other', 'Other'),
    ], string='API Type', default='other', required=True)

    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True
    )

    registration_number = fields.Char(
        string='Registration Number',
        required=True
    )

    account_id = fields.Char(
        string='Account ID',
        required=True
    )

    server_url = fields.Char(
        string='Server URL',
        required=True
    )

    api_key = fields.Char(
        string='API Key',
        required=True,
        groups='base.group_system'
    )

    date_format = fields.Char(
        string='Date Format',
        default='%Y-%m-%d %H:%M:%S'
    )

    timeout = fields.Integer(
        string='Request Timeout',
        default=30
    )

    verify_ssl = fields.Boolean(
        string='Verify SSL',
        default=True
    )

    usable_requests = fields.Integer(
        string='Usable Requests',
        default=100,
        tracking=True
    )

    limit_request = fields.Integer(
        string='Limit Request',
        default=100,
        tracking=True
    )

    reset_period = fields.Selection(
        [
            ('none', 'Manual Only'),
            ('daily', 'Daily'),
            ('monthly', 'Monthly'),
        ],
        string='Reset Period',
        default='none',
        tracking=True
    )

    last_reset_date = fields.Datetime(
        string='Last Reset Date',
        readonly=True
    )

    next_reset_date = fields.Datetime(
        string='Next Reset Date',
        compute='_compute_next_reset_date'
    )

    log_ids = fields.One2many(
        'api.usage.log',
        'config_id',
        string='API Usage Logs'
    )

    reset_history_ids = fields.One2many(
        'api.quota.reset.log',
        'config_id',
        string='Reset History'
    )

    total_input_tokens = fields.Integer(
        string='Total Input Tokens',
        compute='_compute_token_usage'
    )

    total_output_tokens = fields.Integer(
        string='Total Output Tokens',
        compute='_compute_token_usage'
    )

    total_thinking_tokens = fields.Integer(
        string='Total Thinking Tokens',
        compute='_compute_token_usage'
    )

    total_tokens = fields.Integer(
        string='Total Tokens',
        compute='_compute_token_usage'
    )

    total_requests = fields.Integer(
        string='Total Requests',
        compute='_compute_usage'
    )

    successful_requests = fields.Integer(
        string='Successful Requests',
        compute='_compute_usage'
    )

    failed_requests = fields.Integer(
        string='Failed Requests',
        compute='_compute_usage'
    )

    usage_percentage = fields.Float(
        string='Usage Percentage',
        compute='_compute_usage'
    )

    remaining_percentage = fields.Float(
        string='Remaining Percentage',
        compute='_compute_usage'
    )

    @api.depends(
        'log_ids.input_tokens',
        'log_ids.output_tokens',
        'log_ids.thinking_tokens',
        'log_ids.total_tokens'
    )
    def _compute_token_usage(self):
        for rec in self:
            logs = rec.log_ids

            rec.total_input_tokens = sum(logs.mapped('input_tokens'))
            rec.total_output_tokens = sum(logs.mapped('output_tokens'))
            rec.total_thinking_tokens = sum(logs.mapped('thinking_tokens'))
            rec.total_tokens = sum(logs.mapped('total_tokens'))

    @api.depends(
        'log_ids',
        'log_ids.state',
        'usable_requests',
        'limit_request'
    )
    def _compute_usage(self):

        usage_map = {}

        if self.ids:
            grouped_data = self.env['api.usage.log'].read_group(
                [
                    ('config_id', 'in', self.ids)
                ],
                [
                    'config_id',
                    'state'
                ],
                [
                    'config_id',
                    'state'
                ],
                lazy=False
            )

            for item in grouped_data:
                if not item.get('config_id'):
                    continue

                config_id = item['config_id'][0]
                state = item['state']
                count = item['__count']

                usage = usage_map.setdefault(
                    config_id,
                    {
                        'total': 0,
                        'success': 0,
                        'failed': 0,
                    }
                )

                usage['total'] += count

                if state == 'success':
                    usage['success'] += count

                elif state in ('error', 'failed'):
                    usage['failed'] += count

        for rec in self:

            usage = usage_map.get(
                rec.id,
                {}
            )

            rec.total_requests = usage.get('total', 0)
            rec.successful_requests = usage.get('success', 0)
            rec.failed_requests = usage.get('failed', 0)

            if rec.limit_request > 0:

                used = rec.limit_request - rec.usable_requests

                rec.usage_percentage = min(
                    max(used / rec.limit_request * 100, 0),
                    100
                )

                rec.remaining_percentage = min(
                    max(
                        rec.usable_requests / rec.limit_request * 100,
                        0
                    ),
                    100
                )

            else:
                rec.usage_percentage = 0
                rec.remaining_percentage = 0

    @api.depends(
        'reset_period',
        'last_reset_date'
    )
    def _compute_next_reset_date(self):

        for rec in self:

            if not rec.last_reset_date or rec.reset_period == 'none':
                rec.next_reset_date = False

            elif rec.reset_period == 'daily':
                rec.next_reset_date = (
                    rec.last_reset_date + relativedelta(days=1)
                )

            elif rec.reset_period == 'monthly':
                rec.next_reset_date = (
                    rec.last_reset_date + relativedelta(months=1)
                )

            else:
                rec.next_reset_date = False

    @api.constrains(
        'usable_requests',
        'limit_request'
    )
    def _check_request_limit(self):

        for rec in self:

            if rec.limit_request < 0 or rec.usable_requests < 0:
                raise ValidationError(
                    _('Request limits cannot be negative.')
                )

            if rec.usable_requests > rec.limit_request:
                raise ValidationError(
                    _('Usable Requests cannot exceed Limit Request.')
                )

    @api.constrains('timeout')
    def _check_timeout(self):

        for rec in self:

            if rec.timeout <= 0:
                raise ValidationError(
                    _('Request Timeout must be greater than zero.')
                )

    @api.constrains('server_url')
    def _check_server_url(self):

        for rec in self:

            if not rec.server_url:
                continue

            parsed_url = urlparse(rec.server_url)

            if parsed_url.scheme not in ('http', 'https'):
                raise ValidationError(
                    _('Server URL must use HTTP or HTTPS.')
                )

            if not parsed_url.hostname:
                raise ValidationError(
                    _('Invalid Server URL.')
                )

            if parsed_url.username or parsed_url.password:
                raise ValidationError(
                    _('Server URL must not contain credentials.')
                )

    def _reset_quota(self, reset_type='manual'):
        """
        Centralized quota reset method.
        Used by manual action and scheduled cron.
        """

        ResetLog = self.env['api.quota.reset.log'].sudo()

        now = fields.Datetime.now()

        for rec in self:

            old_quota = rec.usable_requests
            new_quota = rec.limit_request

            rec.write({
                'usable_requests': new_quota,
                'last_reset_date': now,
            })

            ResetLog.create({
                'config_id': rec.id,
                'old_quota': old_quota,
                'new_quota': new_quota,
                'reset_type': reset_type,
                'reset_date': now,
                'user_id': self.env.user.id,
            })

            _logger.info(
                'API quota reset: %s (%s)',
                rec.name,
                reset_type
            )

        return True

    def action_reset_quota(self):

        self._reset_quota(reset_type='manual')

        return True

    @api.model
    def cron_reset_quota(self):

        now = fields.Datetime.now()

        configs = self.search([
            ('active', '=', True),
            ('reset_period', 'in', ['daily', 'monthly']),
        ])

        configs_to_reset = self.browse()

        for rec in configs:

            if not rec.last_reset_date:
                configs_to_reset |= rec
                continue

            if rec.reset_period == 'daily':

                should_reset = (
                    rec.last_reset_date.date() < now.date()
                )

            else:

                should_reset = (
                    rec.last_reset_date.year < now.year
                    or (
                        rec.last_reset_date.year == now.year
                        and rec.last_reset_date.month < now.month
                    )
                )

            if should_reset:
                configs_to_reset |= rec

        if configs_to_reset:
            configs_to_reset._reset_quota(
                reset_type='daily_or_monthly'
            )

        return True

    def call_api(
        self,
        endpoint,
        method='GET',
        params=None,
        data=None,
        json=None,
        headers=None,
        timeout=None,
    ):

        self.ensure_one()

        if not self.active:
            raise UserError(
                _('This API configuration is inactive.')
            )

        if not self.server_url or not self.api_key:
            raise UserError(
                _('API configuration is incomplete.')
            )

        method = method.upper()

        if method not in (
            'GET',
            'POST',
            'PUT',
            'PATCH',
            'DELETE'
        ):
            raise UserError(
                _('Unsupported HTTP method.')
            )

        url = (
            self.server_url.rstrip('/')
            + '/'
            + endpoint.lstrip('/')
        )

        request_headers = {
            'X-API-Key': self.api_key,
            'Accept': 'application/json',
        }

        if headers:
            request_headers.update(headers)

        # Reserve quota atomically.

        self.env.cr.execute("""
            UPDATE setting_api_conf
               SET usable_requests = usable_requests - 1
             WHERE id = %s
               AND active = TRUE
               AND usable_requests > 0
         RETURNING usable_requests
        """, [self.id])

        if not self.env.cr.fetchone():
            raise UserError(
                _('API request quota has been exhausted.')
            )

        self.invalidate_recordset([
            'usable_requests'
        ])

        try:

            response = requests.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json,
                headers=request_headers,
                timeout=timeout or self.timeout,
                verify=self.verify_ssl,
            )

        except requests.RequestException as exc:

            # Restore quota because no HTTP response was received.

            self.env.cr.execute("""
                UPDATE setting_api_conf
                   SET usable_requests = LEAST(
                       usable_requests + 1,
                       limit_request
                   )
                 WHERE id = %s
            """, [self.id])

            self.invalidate_recordset([
                'usable_requests'
            ])

            self._create_usage_log(
                endpoint=endpoint,
                method=method,
                state='failed',
                error_message=str(exc)[:2000],
            )

            _logger.exception(
                'API connection failed: %s',
                url
            )

            return {
                'success': False,
                'status_code': False,
                'response': str(exc),
            }

        # Process response.

        success = 200 <= response.status_code < 300

        try:
            response_data = response.json()

        except ValueError:
            response_data = response.text

        self._create_usage_log(
            endpoint=endpoint,
            method=method,
            state='success' if success else 'error',
            status_code=response.status_code,
            response_body=(
                response.text[:5000]
                if response.text else False
            ),
            error_message=(
                False if success
                else response.text[:2000]
            ),
        )

        return {
            'success': success,
            'status_code': response.status_code,
            'response': response_data,
        }

    def _create_usage_log(
        self,
        endpoint,
        method,
        state,
        status_code=False,
        response_body=False,
        error_message=False,
        input_tokens=0,
        output_tokens=0,
        thinking_tokens=0,
    ):

        self.ensure_one()
        return self.env['api.usage.log'].sudo().create({
            'config_id': self.id,
            'endpoint': endpoint,
            'method': method,
            'state': state,
            'status_code': status_code,
            'response_body': response_body,
            'error_message': error_message,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'thinking_tokens': thinking_tokens,
        })

