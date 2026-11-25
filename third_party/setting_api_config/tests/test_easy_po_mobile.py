# -*- coding: utf-8 -*-

import json
from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestEasyPurchaseOrderMobile(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.execution_user = cls.env.ref('base.user_admin')

        cls.customer = cls.env['api.customer'].create({
            'name': 'Mobile PO API Test',
            'code': 'MOBILE_PO_TEST',
            'company_id': cls.company.id,
            'user_id': cls.execution_user.id,
            'included_quota_units': 100,
        })
        cls.endpoint = cls.env['api.endpoint'].create({
            'name': 'Send PO to vendor',
            'code': 'purchase_order_send',
            'path': '/api/v1/purchase/orders/{id}/send',
            'http_method': 'POST',
            'handler_key': 'sample.purchase.order.send',
            'usage_units': 1,
        })
        cls.customer.write({'endpoint_ids': [(4, cls.endpoint.id)]})

        issued = cls.env['api.credential'].issue_for_customer(
            cls.customer, name='Mobile PO Test Key',
        )
        cls.api_key = issued['api_key']

        cls.vendor = cls.env['res.partner'].create({
            'name': 'PO API Test Vendor',
            'supplier_rank': 1,
            'email': 'vendor@example.test',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'PO API Test Product',
            'default_code': 'PO-API-TEST',
            'purchase_ok': True,
            'list_price': 10,
            'standard_price': 7,
        })
        cls.purchase_order = cls.env['purchase.order'].create({
            'partner_id': cls.vendor.id,
            'company_id': cls.company.id,
            'order_line': [(0, 0, {
                'product_id': cls.product.id,
                'product_qty': 3,
                'price_unit': 7,
                'date_planned': '2026-11-09 00:00:00',
            })],
        })
        cls.purchase_order.button_confirm()

        cls.outbound_config = cls.env['setting.api.conf'].create({
            'name': 'Test Vendor API',
            'company_id': cls.company.id,
            'registration_number': 'PO-TEST-REG',
            'account_id': 'PO-TEST-ACCOUNT',
            'api_type': 'other',
            'server_url': 'https://vendor.example.test/api',
            'auth_type': 'api_key',
            'api_key': 'vendor-test-key',
            'usable_requests': 10,
            'limit_request': 10,
            'reset_period': 'none',
        })

    def _post_send(self, api_key=None, order_id=None):
        return self.url_open(
            '/api/v1/purchase/orders/%s/send' % (
                order_id or self.purchase_order.id,
            ),
            data=json.dumps({
                'config_id': self.outbound_config.id,
                'vendor_endpoint': 'purchase/orders',
            }),
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': api_key or self.api_key,
            },
        )

    def test_send_confirmed_purchase_order_to_vendor(self):
        model_class = type(self.env['setting.api.conf'])
        with patch.object(
            model_class,
            'call_api',
            autospec=True,
            return_value={
                'success': True,
                'status_code': 201,
                'response': {'vendor_order_id': 'V-1001'},
                'request_id': 'request-test-1',
            },
        ) as call_api:
            response = self._post_send()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['purchase_order'], self.purchase_order.name)
        self.assertEqual(body['vendor_status_code'], 201)
        self.assertEqual(body['vendor_response']['vendor_order_id'], 'V-1001')

        call_api.assert_called_once()
        call_kwargs = call_api.call_args.kwargs
        self.assertEqual(call_kwargs['endpoint'], 'purchase/orders')
        self.assertEqual(call_kwargs['method'], 'POST')
        po_payload = call_kwargs['json']['purchase_order']
        self.assertEqual(po_payload['name'], self.purchase_order.name)
        self.assertEqual(po_payload['vendor']['name'], self.vendor.name)
        self.assertEqual(po_payload['lines'][0]['product_code'], 'PO-API-TEST')
        self.assertEqual(po_payload['lines'][0]['quantity'], 3)

    def test_reject_invalid_api_key(self):
        response = self._post_send(api_key='invalid-key')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'invalid_api_key')
