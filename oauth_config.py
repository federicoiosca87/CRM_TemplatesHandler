"""
OAuth configuration per deployment environment.

None of these values are secrets — this is a PKCE-only public client.
The client_id is visible in the browser URL bar during the auth flow,
and the redirect URIs are registered in IdentityServer.

Environment resolution order:
  1. ENVIRONMENT  — injected by bego into every deployed container (e.g. "test", "qa")
  2. APP_ENV      — explicit override, useful for direct docker builds / local dev
  3. "local"      — fallback for plain `streamlit run` without any env var
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
    # ENVIRONMENT is injected by bego at runtime; APP_ENV is for local/direct builds.
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "local").lower()
    if env not in _CONFIGS:
        raise ValueError(
            f"Unknown environment '{env}'. Valid values: {list(_CONFIGS.keys())}"
        )
    return _CONFIGS[env]
