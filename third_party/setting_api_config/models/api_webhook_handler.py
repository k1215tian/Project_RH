# ----------------------------------------------------------------------
#  Generic API Webhook Handler
#
#  This model provides a registration mechanism for webhook handlers.
#
#  Responsibilities:
#  - Identify webhook integration.
#  - Validate integration configuration.
#  - Dispatch webhook payload to the appropriate handler.
#
#  Business-specific processing must be implemented by each
#  integration module.
# ----------------------------------------------------------------------

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class APIWebhookHandler(models.Model):

    _name = 'api.webhook.handler'
    _description = 'API Webhook Handler'
    _order = 'id desc'

    name = fields.Char(
        string='Name',
        required=True
    )

    code = fields.Char(
        string='Handler Code',
        required=True,
        index=True
    )

    config_id = fields.Many2one(
        'setting.api.conf',
        string='API Configuration',
        required=True,
        ondelete='cascade'
    )

    active = fields.Boolean(
        default=True
    )

    company_id = fields.Many2one(
        related='config_id.company_id',
        store=True,
        readonly=True
    )

    _sql_constraints = [
        (
            'code_config_unique',
            'unique(code, config_id)',
            'Handler code must be unique per API configuration.'
        ),
    ]

    # ------------------------------------------------------------------
    # Process Incoming Webhook
    #
    #  Dispatches incoming payload to the integration-specific handler.
    # ------------------------------------------------------------------

    def process_webhook(self, payload):

        self.ensure_one()

        if not self.active:
            raise UserError(
                _('Webhook handler is inactive.')
            )

        handler_method = self._get_handler_method()

        return handler_method(payload)

    # ------------------------------------------------------------------
    # Resolve Integration Handler
    #
    #  Integration modules must implement their own handler method.
    # ------------------------------------------------------------------

    def _get_handler_method(self):

        raise NotImplementedError(
            'Webhook handler must be implemented by integration module.'
        )
