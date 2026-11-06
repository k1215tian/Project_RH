# ----------------------------------------------------------------------
#  sample implementation of vendor API integration for sale order
# ----------------------------------------------------------------------
import json

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    api_config_id = fields.Many2one(
        'setting.api.conf',
        string='Vendor API Configuration',
        domain=[
            ('active', '=', True),
            ('api_type', '=', 'e-commerce')
        ]
    )

    vendor_reference = fields.Char(
        string='Vendor Reference',
        readonly=True,
        copy=False
    )

    vendor_sync_state = fields.Selection([
        ('draft', 'Not Sent'),
        ('pending', 'Waiting'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], string='Vendor Sync Status',
        default='draft',
        copy=False,
        tracking=True
    )

    vendor_sync_response = fields.Text(
        string='Vendor Response',
        readonly=True,
        copy=False
    )

    vendor_sync_attempts = fields.Integer(
        string='Sync Attempts',
        default=0,
        copy=False
    )

    vendor_sync_date = fields.Datetime(
        string='Last Sync Date',
        readonly=True,
        copy=False
    )

    vendor_sync_error = fields.Text(
        string='Vendor Sync Error',
        readonly=True,
        copy=False
    )


# ----------------------------------------------------------------------
#  Vendor API Integration Methods akan di simpan di controller atau service terpisah, tapi untuk contoh ini kita simpan di model sale.order
#  contoh ini hanya untuk ilustrasi, implementasi sebenarnya bisa lebih kompleks tergantung kebutuhan
#  contoh ini mengirimkan data order ke vendor API ketika order dikonfirmasi
#  contoh ini juga menangani response dari vendor API dan menyimpan status sinkronisasi di field vendor_sync_state
#  contoh ini juga menangani error dan menyimpan pesan error di field vendor_sync_error
#  contoh ini juga menyimpan response dari vendor API di field vendor_sync_response
#  contoh ini juga menyimpan tanggal sinkronisasi terakhir di field vendor_sync_date
# ----------------------------------------------------------------------
    def _prepare_vendor_payload(self):
        self.ensure_one()
        return {
            'registration_number': self.api_config_id.registration_number,
            'account_id': self.api_config_id.account_id,

            'order_number': self.name,

            'order_date': (
                fields.Date.to_string(self.date_order.date())
                if self.date_order
                else False
            ),


            'customer': {
                'name': self.partner_id.name,
                'email': self.partner_id.email or '',
                'phone': self.partner_id.phone or '',
            },

            'items': [
                {
                    'product': line.product_id.name,
                    'product_code': line.product_id.default_code or '',
                    'quantity': line.product_uom_qty,
                    'price': line.price_unit,
                    'subtotal': line.price_subtotal,
                }
                for line in self.order_line
                if not line.display_type
            ],

            'total_amount': self.amount_total,

            'currency': self.currency_id.name,
        }

    def action_send_to_vendor(self):

        for order in self:

            if not order.api_config_id:
                raise UserError(
                    _('Please select Vendor API Configuration.')
                )

            if order.state != 'sale':
                raise UserError(
                    _('Only confirmed orders can be sent to vendor.')
                )

            if order.vendor_sync_state == 'success':
                raise UserError(
                    _('This order has already been sent successfully.')
                )

            payload = order._prepare_vendor_payload()

            try:

                result = order.api_config_id.call_api(
                    endpoint='/api/orders',
                    method='POST',
                    json=payload,
                    headers={
                        'Content-Type': 'application/json',
                    }
                )

                response = result.get('response', {})

                if result.get('success'):

                    order.write({
                        'vendor_sync_state': 'success',
                        'vendor_sync_response': json.dumps(
                            response,
                            indent=4,
                            ensure_ascii=False
                        ),
                        'vendor_sync_date': fields.Datetime.now(),
                        'vendor_sync_error': False,
                        'vendor_reference': (
                            response.get('order_id')
                            if isinstance(response, dict)
                            else False
                        ),
                    })

                else:

                    error_message = str(response)

                    order.write({
                        'vendor_sync_state': 'failed',
                        'vendor_sync_response': error_message,
                        'vendor_sync_error': error_message,
                        'vendor_sync_date': fields.Datetime.now(),
                    })

            except Exception as exc:

                order.write({
                    'vendor_sync_state': 'failed',
                    'vendor_sync_error': str(exc),
                    'vendor_sync_date': fields.Datetime.now(),
                })

                _logger.exception(
                    'Failed to send Sale Order %s to vendor',
                    order.name
                )

        return True

    def action_confirm(self):

        result = super().action_confirm()

        for order in self:

            if order.api_config_id:
                order.action_send_to_vendor()

        return result
