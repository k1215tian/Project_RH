import ipaddress
import json as json_lib
import logging
import re
import secrets
import socket
import time
import uuid

from urllib.parse import urlsplit

import requests

from requests.auth import HTTPBasicAuth

from dateutil.relativedelta import relativedelta

from odoo import SUPERUSER_ID, api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL


_logger = logging.getLogger(__name__)


class SettingApiConf(models.Model):

    _name = 'setting.api.conf'
    _description = 'Setting API Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'id desc'

    _check_company_auto = True

    HTTP_METHODS = (
        'GET',
        'POST',
        'PUT',
        'PATCH',
        'DELETE',
    )

    MAX_TIMEOUT = 300
    MAX_RESPONSE_SIZE = 1024 * 1024

    HEADER_NAME_PATTERN = re.compile(
        r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
    )

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
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
        tracking=True,
        index=True,
    )

    registration_number = fields.Char(
        string='Registration Number',
        required=True,
    )

    account_id = fields.Char(
        string='Account ID',
        required=True,
    )

    api_type = fields.Selection([
        ('ai', 'Artificial Intelligence'),
        ('payment', 'Payment Gateway'),
        ('shipping', 'Shipping & Logistics'),
        ('communication', 'Communication'),
        ('storage', 'Cloud Storage'),
        ('social', 'Social Media'),
        ('other', 'Other'),
    ],
        string='API Type',
        default='other',
        required=True,
        tracking=True,
    )

    server_url = fields.Char(
        string='Server URL',
        required=True,
    )

    timeout = fields.Integer(
        string='Request Timeout (Seconds)',
        default=30,
        required=True,
    )

    verify_ssl = fields.Boolean(
        string='Verify SSL Certificate',
        default=True,
    )

    allow_private_network = fields.Boolean(
        string='Allow Private Network',
        default=False,
        groups='base.group_system',
        help=(
            'Allow connections to private/internal IP addresses. '
            'Only enable for trusted integrations.'
        ),
    )

    log_response_body = fields.Boolean(
        string='Log Response Body',
        default=False,
        groups='base.group_system',
        help=(
            'Store response body in API usage logs. '
            'Enable only when the response does not contain '
            'sensitive information.'
        ),
    )

    auth_type = fields.Selection([
        ('api_key', 'API Key'),
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Authentication'),
        ('custom', 'Custom Header'),
        ('none', 'No Authentication'),
    ],
        string='Authentication Type',
        default='api_key',
        required=True,
        tracking=True,
    )

    api_key = fields.Char(
        string='API Key / Token',
        groups='base.group_system',
        copy=False,
    )

    auth_username = fields.Char(
        string='Authentication Username',
        groups='base.group_system',
        copy=False,
    )

    auth_password = fields.Char(
        string='Authentication Password',
        groups='base.group_system',
        copy=False,
    )

    auth_header_name = fields.Char(
        string='Custom Header Name',
    )

    auth_header_value = fields.Char(
        string='Custom Header Value',
        groups='base.group_system',
        copy=False,
    )

    credential_id = fields.Many2one(
        'api.credential',
        string='API Credential',
        ondelete='restrict',
    )

    usable_requests = fields.Integer(
        string='Usable Requests',
        default=100,
        tracking=True,
    )

    limit_request = fields.Integer(
        string='Limit Request',
        default=100,
        tracking=True,
    )

    reset_period = fields.Selection([
        ('none', 'Manual Only'),
        ('daily', 'Daily'),
        ('monthly', 'Monthly'),
    ],
        string='Reset Period',
        default='none',
        tracking=True,
    )

    last_reset_date = fields.Datetime(
        string='Last Reset Date',
        readonly=True,
        copy=False,
    )

    next_reset_date = fields.Datetime(
        string='Next Reset Date',
        compute='_compute_next_reset_date',
    )

    date_format = fields.Char(
        string='Date Format',
        default='%Y-%m-%d %H:%M:%S',
    )

    callback_token = fields.Char(
        string='Callback Token',
        copy=False,
        index=True,
        readonly=True,
        default=lambda self: secrets.token_urlsafe(24),
        help='Random token embedded in the callback URL.',
    )

    callback_secret = fields.Char(
        string='Callback Signing Secret',
        groups='base.group_system',
        copy=False,
        help=(
            'Shared secret used to verify the HMAC-SHA256 signature '
            '(X-Signature header) of incoming callbacks.'
        ),
    )

    callback_url = fields.Char(
        string='Callback URL',
        compute='_compute_callback_url',
    )

    callback_ids = fields.One2many(
        'api.callback.log',
        'config_id',
        string='Callbacks',
    )

    _sql_constraints = [
        (
            'callback_token_unique',
            'unique(callback_token)',
            'Callback token must be unique.',
        ),
    ]

    @api.depends('callback_token')
    def _compute_callback_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', ''
        )
        for rec in self:
            rec.callback_url = (
                '%s/api_management/callback/%s' % (
                    base.rstrip('/'), rec.callback_token,
                )
                if rec.callback_token else False
            )

    log_ids = fields.One2many(
        'api.usage.log',
        'config_id',
        string='API Usage Logs',
    )

    reset_history_ids = fields.One2many(
        'api.quota.reset.log',
        'config_id',
        string='Reset History',
    )

    total_input_tokens = fields.Integer(
        compute='_compute_token_usage',
    )

    total_output_tokens = fields.Integer(
        compute='_compute_token_usage',
    )

    total_thinking_tokens = fields.Integer(
        compute='_compute_token_usage',
    )

    total_tokens = fields.Integer(
        compute='_compute_token_usage',
    )

    total_requests = fields.Integer(
        compute='_compute_usage',
    )

    successful_requests = fields.Integer(
        compute='_compute_usage',
    )

    failed_requests = fields.Integer(
        compute='_compute_usage',
    )

    usage_percentage = fields.Float(
        compute='_compute_usage',
    )

    remaining_percentage = fields.Float(
        compute='_compute_usage',
    )

    # =====================================================
    # COMPUTE TOKEN USAGE
    # =====================================================

    @api.depends(
        'log_ids.input_tokens',
        'log_ids.output_tokens',
        'log_ids.thinking_tokens',
    )
    def _compute_token_usage(self):

        grouped_data = {}

        if self.ids:

            result = self.env['api.usage.log'].read_group(
                domain=[
                    ('config_id', 'in', self.ids),
                ],
                fields=[
                    'config_id',
                    'input_tokens:sum',
                    'output_tokens:sum',
                    'thinking_tokens:sum',
                ],
                groupby=[
                    'config_id',
                ],
                lazy=False,
            )

            for item in result:

                if not item.get('config_id'):
                    continue

                config_id = item['config_id'][0]

                grouped_data[config_id] = {
                    'input': item.get('input_tokens', 0) or 0,
                    'output': item.get('output_tokens', 0) or 0,
                    'thinking': item.get('thinking_tokens', 0) or 0,
                }

        for rec in self:

            usage = grouped_data.get(rec.id, {})

            input_tokens = usage.get('input', 0)
            output_tokens = usage.get('output', 0)
            thinking_tokens = usage.get('thinking', 0)

            rec.total_input_tokens = input_tokens
            rec.total_output_tokens = output_tokens
            rec.total_thinking_tokens = thinking_tokens

            rec.total_tokens = (
                input_tokens
                + output_tokens
                + thinking_tokens
            )

    # =====================================================
    # COMPUTE REQUEST STATISTICS
    # =====================================================

    @api.depends(
        'usable_requests',
        'limit_request',
        'log_ids.state',
    )
    def _compute_usage(self):

        usage_map = {}

        if self.ids:

            result = self.env['api.usage.log'].read_group(
                domain=[
                    ('config_id', 'in', self.ids),
                ],
                fields=[
                    'config_id',
                    'state',
                ],
                groupby=[
                    'config_id',
                    'state',
                ],
                lazy=False,
            )

            for item in result:

                if not item.get('config_id'):
                    continue

                config_id = item['config_id'][0]

                usage = usage_map.setdefault(
                    config_id,
                    {
                        'total': 0,
                        'success': 0,
                        'failed': 0,
                    },
                )

                count = item.get('__count', 0)

                usage['total'] += count

                if item.get('state') == 'success':
                    usage['success'] += count

                elif item.get('state') in ('error', 'failed'):
                    usage['failed'] += count

        for rec in self:

            usage = usage_map.get(rec.id, {})

            rec.total_requests = usage.get('total', 0)
            rec.successful_requests = usage.get('success', 0)
            rec.failed_requests = usage.get('failed', 0)

            limit = rec.limit_request
            usable = rec.usable_requests

            if limit > 0:

                used = limit - usable

                rec.usage_percentage = min(
                    max(used / limit * 100, 0),
                    100,
                )

                rec.remaining_percentage = min(
                    max(usable / limit * 100, 0),
                    100,
                )

            else:

                rec.usage_percentage = 0
                rec.remaining_percentage = 0

    # =====================================================
    # COMPUTE NEXT RESET DATE
    # =====================================================

    @api.depends(
        'reset_period',
        'last_reset_date',
    )
    def _compute_next_reset_date(self):

        for rec in self:

            if not rec.last_reset_date:
                rec.next_reset_date = False

            elif rec.reset_period == 'daily':

                rec.next_reset_date = (
                    rec.last_reset_date
                    + relativedelta(days=1)
                )

            elif rec.reset_period == 'monthly':

                rec.next_reset_date = (
                    rec.last_reset_date
                    + relativedelta(months=1)
                )

            else:

                rec.next_reset_date = False

    # =====================================================
    # CONFIGURATION VALIDATION
    # =====================================================

    @api.constrains(
        'usable_requests',
        'limit_request',
    )
    def _check_request_limit(self):

        for rec in self:

            if rec.limit_request < 0 or rec.usable_requests < 0:
                raise ValidationError(_(
                    'Request limits cannot be negative.'
                ))

            if rec.usable_requests > rec.limit_request:
                raise ValidationError(_(
                    'Usable Requests cannot exceed Limit Request.'
                ))

    @api.constrains('timeout')
    def _check_timeout(self):

        for rec in self:

            if not 1 <= rec.timeout <= self.MAX_TIMEOUT:
                raise ValidationError(_(
                    'Request timeout must be between 1 and 300 seconds.'
                ))

    @api.constrains('server_url')
    def _check_server_url(self):

        for rec in self:

            if not rec.server_url:
                continue

            try:

                parsed = urlsplit(rec.server_url)

                port = parsed.port

            except ValueError:

                raise ValidationError(_(
                    'Invalid Server URL.'
                ))

            if parsed.scheme.lower() not in ('http', 'https'):
                raise ValidationError(_(
                    'Server URL must use HTTP or HTTPS.'
                ))

            if not parsed.hostname:
                raise ValidationError(_(
                    'Server URL hostname is required.'
                ))

            if parsed.username or parsed.password:
                raise ValidationError(_(
                    'Server URL must not contain credentials.'
                ))

            if parsed.query or parsed.fragment:
                raise ValidationError(_(
                    'Server URL must not contain query parameters '
                    'or fragments.'
                ))

            if port is not None and not 1 <= port <= 65535:
                raise ValidationError(_(
                    'Invalid Server URL port.'
                ))

            if any(
                ord(char) < 32 or ord(char) == 127
                for char in rec.server_url
            ):
                raise ValidationError(_(
                    'Server URL contains invalid characters.'
                ))

    @api.constrains(
        'auth_type',
        'api_key',
        'auth_username',
        'auth_password',
        'auth_header_name',
        'auth_header_value',
    )
    def _check_authentication(self):

        for rec in self.sudo():

            if rec.auth_type in ('api_key', 'bearer'):

                if not rec.api_key or not rec.api_key.strip():
                    raise ValidationError(_(
                        'API Key / Token is required.'
                    ))

                rec._validate_header_value(rec.api_key)

            elif rec.auth_type == 'basic':

                if not rec.auth_username or not rec.auth_password:
                    raise ValidationError(_(
                        'Username and password are required '
                        'for Basic Authentication.'
                    ))

                rec._validate_header_value(rec.auth_username)
                rec._validate_header_value(rec.auth_password)

            elif rec.auth_type == 'custom':

                if not rec.auth_header_name or not rec.auth_header_value:
                    raise ValidationError(_(
                        'Custom header name and value are required.'
                    ))

                if not self.HEADER_NAME_PATTERN.fullmatch(
                    rec.auth_header_name
                ):
                    raise ValidationError(_(
                        'Invalid custom header name.'
                    ))

                rec._validate_header_value(
                    rec.auth_header_value
                )

    @staticmethod
    def _validate_header_value(value):

        if not isinstance(value, str):
            raise ValidationError(_(
                'HTTP header value must be a string.'
            ))

        if any(
            ord(char) < 32 or ord(char) == 127
            for char in value
        ):
            raise ValidationError(_(
                'HTTP header contains invalid characters.'
            ))

    # =====================================================
    # URL SECURITY
    # =====================================================

    def _validate_outbound_url(self, url):

        self.ensure_one()

        try:

            parsed = urlsplit(url)
            port = parsed.port

        except ValueError:

            raise UserError(_(
                'Invalid outbound API URL.'
            ))

        if (
            parsed.scheme.lower() not in ('http', 'https')
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise UserError(_(
                'Invalid outbound API URL.'
            ))

        if any(
            ord(char) < 32 or ord(char) == 127
            for char in url
        ):
            raise UserError(_(
                'Invalid characters in outbound API URL.'
            ))

        hostname = parsed.hostname

        if self.allow_private_network:
            return True

        # ---------------------------------------------
        # Direct IP validation
        # ---------------------------------------------

        try:

            ip = ipaddress.ip_address(hostname)

            if not ip.is_global:
                raise UserError(_(
                    'Connection to private, reserved or '
                    'non-public IP addresses is not allowed.'
                ))

            return True

        except ValueError:
            pass

        # ---------------------------------------------
        # DNS validation
        # ---------------------------------------------

        try:

            addresses = socket.getaddrinfo(
                hostname,
                port or (
                    443 if parsed.scheme == 'https' else 80
                ),
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )

        except socket.gaierror:

            raise UserError(_(
                'Unable to resolve API hostname.'
            ))

        if not addresses:
            raise UserError(_(
                'API hostname does not resolve.'
            ))

        for address in addresses:

            try:

                ip = ipaddress.ip_address(
                    address[4][0].split('%')[0]
                )

            except ValueError:

                raise UserError(_(
                    'Invalid IP address returned by DNS.'
                ))

            if not ip.is_global:
                raise UserError(_(
                    'Outbound API connection to private, '
                    'reserved or non-public IP addresses '
                    'is not allowed.'
                ))

        return True

    # =====================================================
    # BUILD AUTHENTICATION
    # =====================================================

    def _prepare_auth_headers(self):

        self.ensure_one()

        headers = {
            'Accept': 'application/json',
        }

        if self.auth_type == 'api_key':

            headers['X-API-Key'] = self.api_key

        elif self.auth_type == 'bearer':

            headers['Authorization'] = (
                'Bearer %s' % self.api_key
            )

        elif self.auth_type == 'custom':

            headers[self.auth_header_name] = (
                self.auth_header_value
            )

        return headers

    def _prepare_basic_auth(self):

        self.ensure_one()

        if self.auth_type != 'basic':
            return None

        return HTTPBasicAuth(
            self.auth_username,
            self.auth_password,
        )

    # =====================================================
    # REQUEST VALIDATION
    # =====================================================

    def _prepare_request_url(self, endpoint):

        self.ensure_one()

        if not isinstance(endpoint, str) or not endpoint.strip():
            raise UserError(_(
                'API endpoint is required.'
            ))

        if (
            endpoint.startswith('//')
            or '\\' in endpoint
            or any(
                ord(char) < 32 or ord(char) == 127
                for char in endpoint
            )
        ):
            raise UserError(_(
                'Invalid API endpoint.'
            ))

        try:

            parsed = urlsplit(endpoint)

        except ValueError:

            raise UserError(_(
                'Invalid API endpoint.'
            ))

        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or parsed.path.startswith('//')
        ):
            raise UserError(_(
                'Only relative API endpoints are allowed.'
            ))

        base_url = self.server_url.rstrip('/')

        url = (
            base_url
            + '/'
            + endpoint.lstrip('/')
        )

        self._validate_outbound_url(url)

        return url

    def _prepare_request_headers(self, headers=None):

        self.ensure_one()

        if headers is not None and not isinstance(headers, dict):
            raise UserError(_(
                'Headers must be a dictionary.'
            ))

        request_headers = {}

        for name, value in (headers or {}).items():

            if not isinstance(name, str) or not isinstance(value, str):
                raise UserError(_(
                    'HTTP header names and values must be strings.'
                ))

            if not self.HEADER_NAME_PATTERN.fullmatch(name):
                raise UserError(_(
                    'Invalid HTTP header name.'
                ))

            self._validate_header_value(value)

            if name.lower() in (
                'host',
                'content-length',
                'transfer-encoding',
            ):
                raise UserError(_(
                    'This HTTP header cannot be overridden.'
                ))

            request_headers[name] = value

        # Authentication has priority over caller headers.
        for name, value in self._prepare_auth_headers().items():

            for existing_name in list(request_headers):

                if existing_name.lower() == name.lower():
                    del request_headers[existing_name]

            request_headers[name] = value

        return request_headers

    # =====================================================
    # QUOTA MANAGEMENT
    # =====================================================

    def _reserve_request_quota(self):
        """
        Reserve one request.

        Runs in its OWN cursor and commits immediately, so that:
        * the config row is not locked while we wait for the remote server;
        * the reservation survives a rollback of the caller.

        Do not write to this config record in the caller's transaction
        before calling call_api(), otherwise this UPDATE waits for that lock.
        """

        self.ensure_one()

        with self.pool.cursor() as cr:
            cr.execute(SQL("""
                UPDATE setting_api_conf
                   SET usable_requests = usable_requests - 1,
                       write_date = NOW() AT TIME ZONE 'UTC',
                       write_uid = %s
                 WHERE id = %s
                   AND active = TRUE
                   AND usable_requests > 0
             RETURNING usable_requests
            """, self.env.uid, self.id))
            result = cr.fetchone()

        if not result:
            raise UserError(_(
                'API request quota has been exhausted '
                'or configuration is inactive.'
            ))

        self.invalidate_recordset([
            'usable_requests',
            'write_date',
            'write_uid',
        ])

        return result[0]

    def _refund_request_quota(self):

        self.ensure_one()

        with self.pool.cursor() as cr:
            cr.execute(SQL("""
                UPDATE setting_api_conf
                   SET usable_requests = LEAST(
                           usable_requests + 1,
                           limit_request
                       ),
                       write_date = NOW() AT TIME ZONE 'UTC',
                       write_uid = %s
                 WHERE id = %s
            """, self.env.uid, self.id))

        self.invalidate_recordset([
            'usable_requests',
            'write_date',
            'write_uid',
        ])

        return True

    # =====================================================
    # USAGE LOG
    # =====================================================

    def _create_usage_log(
        self,
        endpoint,
        method,
        state,
        status_code=0,
        response_body=False,
        error_message=False,
        input_tokens=0,
        output_tokens=0,
        thinking_tokens=0,
        duration_ms=0,
        request_id=False,
        external_reference=False,
        callback_state='none',
    ):
        """
        Create the usage log in its own cursor so it is kept even when the
        caller's transaction is rolled back. Never raises.
        """

        self.ensure_one()

        vals = {
            'config_id': self.id,
            'direction': 'outbound',
            'request_id': request_id or False,
            'external_reference': external_reference or False,
            'endpoint': (endpoint or '')[:1000],
            'method': method,
            'state': state,
            'status_code': status_code or 0,
            'response_body': response_body,
            'error_message': error_message,
            'duration_ms': duration_ms,
            'usage_units': 1,
            'billable_units': 0,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'thinking_tokens': thinking_tokens,
            'callback_state': callback_state,
        }

        try:
            with self.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                return env['api.usage.log'].create(vals).id
        except Exception:
            _logger.exception(
                'Failed to create API usage log: config_id=%s', self.id,
            )
            return False

    # =====================================================
    # QUOTA RESET
    # =====================================================

    def _reset_quota(self, reset_type='manual', only_if_due=False):

        self.ensure_one()

        now = fields.Datetime.now()

        self.flush_recordset([
            'usable_requests',
            'limit_request',
            'last_reset_date',
            'reset_period',
        ])

        # Lock the row before checking and updating quota.
        self.env.cr.execute(SQL("""
            SELECT usable_requests,
                   limit_request,
                   last_reset_date,
                   reset_period
              FROM setting_api_conf
             WHERE id = %s
               FOR UPDATE
        """, self.id))

        result = self.env.cr.fetchone()

        if not result:
            return False

        old_quota, new_quota, last_reset, period = result

        # Cron passes 'automatic'; the log selection stores the period.
        if reset_type == 'automatic':
            reset_type = period if period in ('daily', 'monthly') else 'manual'

        if only_if_due:

            should_reset = False

            if period == 'daily':

                should_reset = (
                    not last_reset
                    or last_reset.date() < now.date()
                )

            elif period == 'monthly':

                should_reset = (
                    not last_reset
                    or last_reset.year < now.year
                    or (
                        last_reset.year == now.year
                        and last_reset.month < now.month
                    )
                )

            if not should_reset:
                return False

        # Update quota.
        self.env.cr.execute(SQL("""
            UPDATE setting_api_conf
               SET usable_requests = limit_request,
                   last_reset_date = %s,
                   write_date = NOW(),
                   write_uid = %s
             WHERE id = %s
        """, now, self.env.uid, self.id))

        self.invalidate_recordset([
            'usable_requests',
            'limit_request',
            'last_reset_date',
            'write_date',
            'write_uid',
        ])

        # Create reset history.
        self.env['api.quota.reset.log'].sudo().create({

            'config_id': self.id,

            'old_quota': old_quota,

            'new_quota': new_quota,

            'reset_type': reset_type,

            'reset_date': now,

            'user_id': self.env.uid,

        })

        _logger.info(
            'API quota reset: config_id=%s, type=%s',
            self.id,
            reset_type,
        )

        return True

    def action_reset_quota(self):

        self.ensure_one()

        self.check_access('write')

        self._reset_quota(
            reset_type='manual',
        )

        return True

    # =====================================================
    # CRON RESET
    # =====================================================

    @api.model
    def cron_reset_quota(self):

        configs = self.sudo().search([
            ('active', '=', True),
            ('reset_period', 'in', [
                'daily',
                'monthly',
            ]),
        ])

        for config in configs:

            try:

                with self.env.cr.savepoint():

                    config._reset_quota(
                        reset_type='automatic',
                        only_if_due=True,
                    )

            except Exception:

                _logger.exception(
                    'Failed to reset API quota: config_id=%s',
                    config.id,
                )

        return True

    # =====================================================
    # OUTBOUND API CLIENT
    # =====================================================

    @staticmethod
    def _decode_body(content, encoding):
        try:
            return content.decode(encoding or 'utf-8', errors='replace')
        except LookupError:
            return content.decode('utf-8', errors='replace')

    def _read_limited_body(self, response):
        """Return (bytes, too_large). Never buffers more than the limit."""

        content = bytearray()

        for chunk in response.iter_content(chunk_size=8192):

            if not chunk:
                continue

            content.extend(chunk)

            if len(content) > self.MAX_RESPONSE_SIZE:
                return bytes(content[:self.MAX_RESPONSE_SIZE]), True

        return bytes(content), False

    def _extract_external_reference(self, response_data):
        """
        Hook: return the provider-side id used to match a later callback.
        Override per provider.
        """

        if isinstance(response_data, dict):
            value = response_data.get('id') or response_data.get('reference')

            if isinstance(value, (str, int)) and not isinstance(value, bool):
                return str(value)[:255]

        return False

    def call_api(
        self,
        endpoint,
        method='GET',
        params=None,
        data=None,
        json=None,
        headers=None,
        timeout=None,
        input_tokens=0,
        output_tokens=0,
        thinking_tokens=0,
        expect_callback=False,
        request_id=False,
    ):
        """
        Call the provider API, meter the request and log the result.

        NOTE: the `json` argument shadows the json module, therefore the
        module is imported as json_lib.
        """

        self.ensure_one()

        # ---------------------------------------------
        # ACCESS VALIDATION (as the calling user)
        # ---------------------------------------------

        self.check_access('read')

        if self.company_id not in self.env.companies:
            raise UserError(_(
                'You cannot use an API configuration '
                'from another company.'
            ))

        if not self.active:
            raise UserError(_(
                'This API configuration is inactive.'
            ))

        # api_key, auth_*, allow_private_network, log_response_body are
        # restricted to base.group_system. After the checks above, read
        # them with sudo so normal users can still use the integration.
        self = self.sudo()

        if not isinstance(method, str):
            raise UserError(_('Invalid HTTP method.'))

        method = method.upper()

        if method not in self.HTTP_METHODS:
            raise UserError(_('Unsupported HTTP method.'))

        if data is not None and json is not None:
            raise UserError(_(
                'You cannot use both data and json payload.'
            ))

        for value in (input_tokens, output_tokens, thinking_tokens):

            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise UserError(_(
                    'Token usage must be a non-negative integer.'
                ))

        url = self._prepare_request_url(endpoint)

        request_timeout = (
            self.timeout if timeout is None else timeout
        )

        if (
            isinstance(request_timeout, bool)
            or not isinstance(request_timeout, (int, float))
            or not 0 < request_timeout <= self.MAX_TIMEOUT
        ):
            raise UserError(_(
                'Request timeout must be between '
                '1 and 300 seconds.'
            ))

        request_id = request_id or uuid.uuid4().hex

        request_headers = self._prepare_request_headers(headers=headers)
        request_headers['X-Request-ID'] = request_id

        auth = self._prepare_basic_auth()

        callback_state = 'pending' if expect_callback else 'none'

        # ---------------------------------------------
        # RESERVE QUOTA (own cursor, committed)
        # ---------------------------------------------

        self._reserve_request_quota()

        started = time.monotonic()
        response = None

        try:

            with requests.Session() as session:

                # Avoid implicit proxy/environment settings.
                session.trust_env = False

                response = session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    headers=request_headers,
                    auth=auth,
                    timeout=request_timeout,
                    verify=self.verify_ssl,
                    allow_redirects=False,
                    stream=True,
                )

                response_bytes, too_large = self._read_limited_body(response)

                duration_ms = int((time.monotonic() - started) * 1000)
                status_code = response.status_code
                text = self._decode_body(response_bytes, response.encoding)

                if too_large:

                    message = _(
                        'API response exceeds the maximum '
                        'allowed size of 1 MB.'
                    )

                    self._create_usage_log(
                        endpoint=endpoint,
                        method=method,
                        state='error',
                        status_code=status_code,
                        error_message=message,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        thinking_tokens=thinking_tokens,
                        duration_ms=duration_ms,
                        request_id=request_id,
                    )

                    return {
                        'success': False,
                        'status_code': status_code,
                        'response': message,
                        'request_id': request_id,
                    }

                # response.content cannot be used: the body was already
                # consumed by iter_content() (stream=True), so response.json()
                # would raise RuntimeError. Parse our own buffer instead.
                try:
                    response_data = json_lib.loads(text)
                except ValueError:
                    response_data = text

                success = 200 <= status_code < 300

                self._create_usage_log(
                    endpoint=endpoint,
                    method=method,
                    state='success' if success else 'error',
                    status_code=status_code,
                    response_body=text[:5000] if self.log_response_body else False,
                    error_message=False if success else text[:2000],
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    thinking_tokens=thinking_tokens,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    external_reference=(
                        self._extract_external_reference(response_data)
                        if success else False
                    ),
                    callback_state=callback_state if success else 'none',
                )

                return {
                    'success': success,
                    'status_code': status_code,
                    'response': response_data,
                    'request_id': request_id,
                }

        except requests.RequestException as exc:

            # Quota is intentionally NOT refunded: a timeout does not prove
            # that the remote server did not process the request.

            self._create_usage_log(
                endpoint=endpoint,
                method=method,
                state='failed',
                error_message=(
                    '%s: %s' % (type(exc).__name__, str(exc))
                )[:2000],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
                duration_ms=int((time.monotonic() - started) * 1000),
                request_id=request_id,
            )

            _logger.warning(
                'API request failed: config_id=%s, exception=%s',
                self.id,
                type(exc).__name__,
            )

            return {
                'success': False,
                'status_code': False,
                'response': str(exc),
                'request_id': request_id,
            }

        finally:

            if response is not None:
                response.close()
