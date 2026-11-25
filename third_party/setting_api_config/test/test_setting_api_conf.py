# -*- coding: utf-8 -*-

from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError

from requests.exceptions import ConnectionError, Timeout


@tagged('post_install', '-at_install')
class TestSettingApiConf(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.ApiConfig = cls.env['setting.api.conf']

        cls.config = cls.ApiConfig.create({

            'name': 'Test API Configuration',

            'auth_type': 'api_key',
            'api_key': 'test-api-key',

            'api_type': 'other',

            'registration_number': 'REG-001',
            'account_id': 'ACC-001',

            'server_url': 'https://example.com',

            'timeout': 30,

            'usable_requests': 10,
            'limit_request': 10,

            'reset_period': 'none',

        })

    # =================================================
    # HELPER
    # =================================================

    def _mock_response(
        self,
        status_code=200,
        response_json=None,
        response_text='',
    ):

        response = MagicMock()

        response.status_code = status_code
        response.text = response_text

        response.json.return_value = (
            response_json
            if response_json is not None
            else {}
        )

        return response

    # =================================================
    # BASIC CONFIGURATION
    # =================================================

    def test_create_configuration(self):

        self.assertTrue(self.config.id)

        self.assertEqual(
            self.config.usable_requests,
            10,
        )

        self.assertEqual(
            self.config.limit_request,
            10,
        )

    # =================================================
    # VALIDATION: QUOTA
    # =================================================

    def test_negative_quota(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'usable_requests': -1,
            })

    def test_usable_requests_exceed_limit(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'usable_requests': 20,
            })

    # =================================================
    # VALIDATION: TIMEOUT
    # =================================================

    def test_invalid_timeout(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'timeout': 500,
            })

    # =================================================
    # VALIDATION: URL
    # =================================================

    def test_invalid_server_url_scheme(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'server_url': 'ftp://example.com',
            })

    def test_server_url_with_credentials(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'server_url': 'https://user:password@example.com',
            })

    def test_server_url_with_query(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'server_url': 'https://example.com?token=123',
            })

    # =================================================
    # VALIDATION: AUTHENTICATION
    # =================================================

    def test_missing_api_key(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'api_key': False,
            })

    def test_basic_auth_validation(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'auth_type': 'basic',
                'auth_username': 'test',
                'auth_password': False,
            })

    def test_custom_header_validation(self):

        with self.assertRaises(ValidationError):

            self.config.write({
                'auth_type': 'custom',
                'auth_header_name': 'Invalid Header',
                'auth_header_value': 'test',
            })

    # =================================================
    # AUTHENTICATION HEADERS
    # =================================================

    def test_api_key_headers(self):

        headers = self.config._prepare_auth_headers()

        self.assertEqual(
            headers['X-API-Key'],
            'test-api-key',
        )

    def test_bearer_headers(self):

        self.config.write({
            'auth_type': 'bearer',
            'api_key': 'bearer-token',
        })

        headers = self.config._prepare_auth_headers()

        self.assertEqual(
            headers['Authorization'],
            'Bearer bearer-token',
        )

    def test_basic_auth(self):

        self.config.write({
            'auth_type': 'basic',
            'auth_username': 'username',
            'auth_password': 'password',
        })

        auth = self.config._prepare_basic_auth()

        self.assertIsNotNone(auth)

        self.assertEqual(
            auth.username,
            'username',
        )

        self.assertEqual(
            auth.password,
            'password',
        )

    def test_no_authentication(self):

        self.config.write({
            'auth_type': 'none',
        })

        headers = self.config._prepare_auth_headers()

        self.assertEqual(
            headers,
            {
                'Accept': 'application/json',
            },
        )

    # =================================================
    # QUOTA RESERVATION
    # =================================================

    def test_reserve_quota(self):

        remaining = self.config._reserve_request_quota()

        self.assertEqual(
            remaining,
            9,
        )

        self.assertEqual(
            self.config.usable_requests,
            9,
        )

    def test_quota_exhausted(self):

        self.config.write({
            'usable_requests': 0,
        })

        with self.assertRaises(UserError):

            self.config._reserve_request_quota()

    def test_inactive_configuration_cannot_reserve_quota(self):

        self.config.write({
            'active': False,
        })

        with self.assertRaises(UserError):

            self.config._reserve_request_quota()

    # =================================================
    # QUOTA REFUND
    # =================================================

    def test_refund_quota(self):

        self.config.write({
            'usable_requests': 5,
        })

        self.config._refund_request_quota()

        self.assertEqual(
            self.config.usable_requests,
            6,
        )

    def test_refund_does_not_exceed_limit(self):

        self.config.write({
            'usable_requests': 10,
        })

        self.config._refund_request_quota()

        self.assertEqual(
            self.config.usable_requests,
            10,
        )

    # =================================================
    # OUTBOUND URL SECURITY
    # =================================================

    def test_private_ip_blocked(self):

        with self.assertRaises(UserError):

            self.config._validate_outbound_url(
                'http://127.0.0.1:8069'
            )

    def test_private_network_allowed(self):

        self.config.allow_private_network = True

        result = self.config._validate_outbound_url(
            'http://127.0.0.1:8069'
        )

        self.assertTrue(result)

    def test_invalid_outbound_url(self):

        with self.assertRaises(UserError):

            self.config._validate_outbound_url(
                'ftp://example.com'
            )

    def test_public_ip_allowed(self):

        result = self.config._validate_outbound_url(
            'https://8.8.8.8'
        )

        self.assertTrue(result)

    # =================================================
    # API REQUEST SUCCESS
    # =================================================

    @patch.object(
        type(config) if False else object,
        'unused',
        create=True,
    )
    def test_dummy(self):
        pass

    def test_call_api_success(self):

        response = self._mock_response(
            status_code=200,
            response_json={
                'message': 'success',
            },
            response_text='{"message": "success"}',
        )

        with patch.object(
            type(self.config),
            '_validate_outbound_url',
            return_value=True,
        ), patch.object(
            type(self.config),
            '_create_usage_log',
        ) as mock_log, patch(
            'odoo.addons.your_module.models.setting_api_conf.requests.request',
            return_value=response,
        ) as mock_request:

            result = self.config.call_api(
                endpoint='/api/test',
                method='GET',
            )

            self.assertTrue(result['success'])

            self.assertEqual(
                result['status_code'],
                200,
            )

            self.assertEqual(
                result['response']['message'],
                'success',
            )

            self.assertEqual(
                self.config.usable_requests,
                9,
            )

            mock_request.assert_called_once()
            mock_log.assert_called_once()

            response.close.assert_called_once()

    # =================================================
    # API REQUEST ERROR
    # =================================================

    def test_call_api_http_error(self):

        response = self._mock_response(
            status_code=500,
            response_json={
                'error': 'Internal Server Error',
            },
            response_text='Internal Server Error',
        )

        with patch.object(
            type(self.config),
            '_validate_outbound_url',
            return_value=True,
        ), patch.object(
            type(self.config),
            '_create_usage_log',
        ) as mock_log, patch(
            'odoo.addons.your_module.models.setting_api_conf.requests.request',
            return_value=response,
        ):

            result = self.config.call_api(
                endpoint='api/test',
            )

            self.assertFalse(result['success'])

            self.assertEqual(
                result['status_code'],
                500,
            )

            # HTTP 500 still consumes quota.
            self.assertEqual(
                self.config.usable_requests,
                9,
            )

            mock_log.assert_called_once()

            response.close.assert_called_once()

    # =================================================
    # CONNECTION ERROR
    # =================================================

    def test_call_api_connection_error(self):

        with patch.object(
            type(self.config),
            '_validate_outbound_url',
            return_value=True,
        ), patch.object(
            type(self.config),
            '_create_usage_log',
        ) as mock_log, patch(
            'odoo.addons.your_module.models.setting_api_conf.requests.request',
            side_effect=ConnectionError('Connection failed'),
        ):

            result = self.config.call_api(
                endpoint='api/test',
            )

            self.assertFalse(result['success'])

            self.assertFalse(result['status_code'])

            # Connection failure refunds quota.
            self.assertEqual(
                self.config.usable_requests,
                10,
            )

            mock_log.assert_called_once()

    # =================================================
    # TIMEOUT ERROR
    # =================================================

    def test_call_api_timeout(self):

        with patch.object(
            type(self.config),
            '_validate_outbound_url',
            return_value=True,
        ), patch.object(
            type(self.config),
            '_create_usage_log',
        ), patch(
            'odoo.addons.your_module.models.setting_api_conf.requests.request',
            side_effect=Timeout('Request timeout'),
        ):

            result = self.config.call_api(
                endpoint='api/test',
            )

            self.assertFalse(result['success'])

            self.assertEqual(
                self.config.usable_requests,
                10,
            )

    # =================================================
    # REQUEST VALIDATION
    # =================================================

    def test_invalid_http_method(self):

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='api/test',
                method='TRACE',
            )

    def test_empty_endpoint(self):

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='',
            )

    def test_absolute_endpoint_blocked(self):

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='https://evil.com/api',
            )

    def test_endpoint_protocol_relative_blocked(self):

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='//evil.com/api',
            )

    def test_inactive_configuration_blocked(self):

        self.config.active = False

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='api/test',
            )

    def test_data_and_json_cannot_be_used_together(self):

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='api/test',
                data={'name': 'test'},
                json={'name': 'test'},
            )

    def test_invalid_request_timeout(self):

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='api/test',
                timeout=500,
            )

    def test_invalid_token_usage(self):

        with self.assertRaises(UserError):

            self.config.call_api(
                endpoint='api/test',
                input_tokens=-1,
            )

    # =================================================
    # QUOTA RESET
    # =================================================

    def test_manual_quota_reset(self):

        self.config.write({
            'usable_requests': 2,
            'limit_request': 10,
        })

        self.config.action_reset_quota()

        self.assertEqual(
            self.config.usable_requests,
            10,
        )

        self.assertTrue(
            self.config.last_reset_date
        )

        self.assertEqual(
            self.config.reset_history_ids[-1].reset_type,
            'manual',
        )

    # =================================================
    # COMPUTE NEXT RESET
    # =================================================

    def test_next_reset_date_daily(self):

        reset_date = '2026-01-01 10:00:00'

        self.config.write({
            'reset_period': 'daily',
            'last_reset_date': reset_date,
        })

        self.assertTrue(
            self.config.next_reset_date
        )

        self.assertEqual(
            self.config.next_reset_date.date(),
            fields.Date.to_date('2026-01-02'),
        )

    def test_next_reset_date_manual(self):

        self.config.write({
            'reset_period': 'none',
        })

        self.assertFalse(
            self.config.next_reset_date
        )
