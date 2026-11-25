import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApiEndpoint(models.Model):
    _name = "api.endpoint"
    _description = "API Endpoint"
    _order = "code"

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)

    path = fields.Char(required=True, help="Example: /sales/orders or /sales/orders/{id}")

    http_method = fields.Selection(
        [("GET", "GET"), ("POST", "POST"), ("PUT", "PUT"),
         ("PATCH", "PATCH"), ("DELETE", "DELETE")],
        required=True, default="GET",
    )

    handler_key = fields.Char(required=True, help="Trusted handler identifier.")
    description = fields.Text()
    active = fields.Boolean(default=True)

    usage_units = fields.Integer(string="Usage Units", default=1, required=True)
    max_request_size = fields.Integer(string="Max Request Size (Bytes)", default=1048576)

    processing_mode = fields.Selection(
        [("sync", "Synchronous"), ("async", "Asynchronous")],
        default="sync", required=True,
    )

    _sql_constraints = [
        ("api_endpoint_code_unique", "unique(code)", "Endpoint code must be unique."),
        ("api_endpoint_route_unique", "unique(http_method, path)",
         "This HTTP method and path is already registered."),
        ("api_endpoint_units_positive", "CHECK(usage_units > 0)",
         "Usage units must be greater than zero."),
        ("api_endpoint_size_positive", "CHECK(max_request_size > 0)",
         "Max request size must be greater than zero."),
    ]

    @api.constrains("path")
    def _check_path(self):
        for rec in self:
            path = rec.path or ""
            if (
                not re.fullmatch(r"/[A-Za-z0-9._~/{}-]*", path)
                or "//" in path
                or ".." in path
            ):
                raise ValidationError(_(
                    "Path must start with '/' and contain only letters, "
                    "digits and . _ ~ - / { }"
                ))
