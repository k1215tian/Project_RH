# -*- coding: utf-8 -*-

import hashlib
import hmac
import secrets

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class ApiCredential(models.Model):
    _name = "api.credential"
    _description = "API Customer Credential"
    _order = "create_date desc"

    name = fields.Char(
        string="Credential Name",
        required=True,
    )

    customer_id = fields.Many2one(
        comodel_name="api.customer",
        string="API Customer",
        required=True,
        ondelete="restrict",
        index=True,
    )

    company_id = fields.Many2one(
        related="customer_id.company_id",
        store=True,
        index=True,
    )

    key_prefix = fields.Char(
        string="Key Prefix",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    secret_hash = fields.Char(
        string="Secret Hash",
        required=True,
        readonly=True,
        copy=False,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    revoked_at = fields.Datetime(
        string="Revoked At",
        readonly=True,
        copy=False,
    )

    expires_at = fields.Datetime(
        string="Expiration Date",
        copy=False,
    )

    last_used_at = fields.Datetime(
        string="Last Used At",
        readonly=True,
        copy=False,
    )

    last_used_ip = fields.Char(
        string="Last Used IP",
        readonly=True,
        copy=False,
    )

    _sql_constraints = [
        (
            "api_credential_prefix_unique",
            "UNIQUE(key_prefix)",
            "API credential prefix must be unique.",
        ),
    ]


    @api.model
    def _generate_secret(self):
        """
        Generate cryptographically secure random secret.
        """

        return secrets.token_urlsafe(32)

    @api.model
    def _hash_secret(self, secret):
        """
        Store only the SHA-256 hash of the secret.
        """

        return hashlib.sha256(
            secret.encode("utf-8")
        ).hexdigest()

    @api.model
    def _verify_secret(self, secret, secret_hash):
        """
        Constant-time comparison.
        """

        candidate_hash = self._hash_secret(secret)

        return hmac.compare_digest(
            candidate_hash,
            secret_hash or "",
        )

    @api.model
    def issue_for_customer(self, customer, name="Production API Key",
                           expires_at=False):
        """
        Generate a new API credential.

        IMPORTANT:
        The plaintext API key is returned only once.
        It is never stored in the database.
        """

        if not self.env.user.has_group(
            "setting_api_config.group_api_manager"
        ):
            raise AccessError(
                _("Only API Managers can issue API credentials.")
            )

        customer.ensure_one()

        if not customer.active:
            raise ValidationError(
                _("Cannot issue credentials for an inactive customer.")
            )

        secret = self._generate_secret()

        random_id = secrets.token_hex(6)

        prefix = (
            f"ak_live_{customer.code}_{random_id}"
        )

        api_key = f"{prefix}.{secret}"

        credential = self.create({
            "name": name,
            "customer_id": customer.id,
            "key_prefix": prefix,
            "secret_hash": self._hash_secret(secret),
            "expires_at": expires_at or False,
            "active": True,
        })

        return {
            "credential_id": credential.id,
            "credential_name": credential.name,
            "api_key": api_key,
            "key_prefix": prefix,
        }

    @api.model
    def authenticate_api_key(self, api_key):
        """
        Authenticate API key.

        Expected format:
            ak_live_customer_randomid.secret
        """

        if not api_key or not isinstance(api_key, str):
            return False

        if "." not in api_key:
            return False

        prefix, secret = api_key.split(".", 1)

        if not prefix or not secret:
            return False

        credential = self.sudo().search([
            ("key_prefix", "=", prefix),
            ("active", "=", True),
        ], limit=1)

        if not credential:
            return False

        if not credential.customer_id.active:
            return False

        now = fields.Datetime.now()

        if credential.expires_at and (
            credential.expires_at <= now
        ):
            return False

        if not self._verify_secret(
            secret,
            credential.secret_hash,
        ):
            return False

        return credential


    def action_mark_as_used(self, client_ip=False):
        """
        Update credential last-used information.
        """

        self.ensure_one()

        # Throttle: avoid a write (row lock + WAL) on every single request.
        now = fields.Datetime.now()

        if (
            self.last_used_at
            and self.last_used_ip == (client_ip or False)
            and (now - self.last_used_at).total_seconds() < 60
        ):
            return True

        self.sudo().write({
            "last_used_at": fields.Datetime.now(),
            "last_used_ip": client_ip or False,
        })

        return True

    # ---------------------------------------------------------
    # REVOKE CREDENTIAL
    # ---------------------------------------------------------

    def action_revoke(self):
        """
        Immediately disable an API credential.
        """

        for credential in self:
            if not self.env.user.has_group(
                "setting_api_config.group_api_manager"
            ):
                raise AccessError(
                    _("Only API Managers can revoke credentials.")
                )

            if credential.active:
                credential.write({
                    "active": False,
                    "revoked_at": fields.Datetime.now(),
                })

        return True

    # ---------------------------------------------------------
    # REACTIVATE CREDENTIAL
    # ---------------------------------------------------------

    def action_reactivate(self):
        """
        Reactivate a credential that has not expired.
        """

        for credential in self:
            if not self.env.user.has_group(
                "setting_api_config.group_api_manager"
            ):
                raise AccessError(
                    _("Only API Managers can reactivate credentials.")
                )

            if (
                credential.expires_at
                and credential.expires_at <= fields.Datetime.now()
            ):
                raise ValidationError(
                    _("Expired credentials cannot be reactivated.")
                )

            credential.write({
                "active": True,
                "revoked_at": False,
            })

        return True

    # ---------------------------------------------------------
    # CONSTRAINTS
    # ---------------------------------------------------------

    @api.constrains("expires_at")
    def _check_expiration(self):
        for credential in self:
            if (
                credential.expires_at
                and credential.create_date
                and credential.expires_at <= credential.create_date
            ):
                raise ValidationError(
                    _("Expiration date must be later than creation date.")
                )
