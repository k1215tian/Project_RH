from odoo import models, _
from odoo.exceptions import AccessError


class ApiProviderHandler(models.AbstractModel):
    _name = "api.provider.handler"
    _description = "API Provider Handler"

    def _get_handler_map(self):
        """
        Integration modules extend this method:

            def _get_handler_map(self):
                res = super()._get_handler_map()
                res["sales.order.create"] = self._handle_order_create
                return res
        """
        return {}

    def _dispatch(self, handler_key, payload, path_params, customer=None):
        # Run the handler as the customer's API execution user, so ACL and
        # record rules are enforced instead of running with a privileged env.
        if customer:
            self = self.with_user(customer.user_id).with_company(customer.company_id)

        handler = self._get_handler_map().get(handler_key)

        if not callable(handler):
            raise AccessError(_("API handler is not registered."))

        return handler(payload, path_params)
