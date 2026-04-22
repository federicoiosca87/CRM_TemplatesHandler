"""
OAuth configuration per deployment environment.

None of these values are secrets — this is a PKCE-only public client.
The client_id is visible in the browser URL bar during the auth flow,
and the redirect URIs are registered in IdentityServer.

The active environment is selected by the APP_ENV environment variable.
Defaults to "local" when not set (local development).
"""

import os

_CONFIGS: dict[str, dict] = {
    "local": {
        "authority": "https://identity-server.test.betsson.tech",
        "client_id": "POC.CRM.TemplateHandler",
        "client_secret": "",
        "scopes": "openid profile email",
        "redirect_uri": "http://localhost:8080",
    },
    "test": {
        "authority": "https://identity-server.test.betsson.tech",
        "client_id": "POC.CRM.TemplateHandler",
        "client_secret": "",
        "scopes": "openid profile email",
        "redirect_uri": "https://crm-templates-handler-test.apps.igaming-test.euc1.betsson.tech",
    },
    "qa": {
        "authority": "https://identity-server.test.betsson.tech",
        "client_id": "POC.CRM.TemplateHandler",
        "client_secret": "",
        "scopes": "openid profile email",
        "redirect_uri": "https://crm-templates-handler-qa.apps.igaming-test.euc1.betsson.tech",
    },
}


def get_oauth_config() -> dict:
    env = os.environ.get("APP_ENV", "local").lower()
    if env not in _CONFIGS:
        raise ValueError(
            f"Unknown APP_ENV '{env}'. Valid values: {list(_CONFIGS.keys())}"
        )
    return _CONFIGS[env]
