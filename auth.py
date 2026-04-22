"""
OAuth 2.0 authentication for CRM Template Generator (Streamlit).

Flow: Authorization Code + PKCE against a Betsson IdentityServer instance.

Configuration is loaded from oauth_config.py, keyed by the APP_ENV environment
variable (defaults to "local"). No secrets or env vars are needed beyond APP_ENV.

Usage (in app.py, immediately after st.set_page_config):
    from auth import require_auth
    require_auth()
"""

import base64
import hashlib
import html as html_lib
import os
import secrets as _secrets
import urllib.parse

import requests
import streamlit as st

from oauth_config import get_oauth_config

# ---------------------------------------------------------------------------
# Server-side PKCE verifier cache
#
# Maps OAuth `state` token → PKCE code verifier.
# Lives in module memory, so it survives the browser round-trip to the
# external OAuth provider and back.  Works correctly for single-instance
# deployments (local and containerised QA/prod).
# ---------------------------------------------------------------------------
_pkce_cache: dict[str, str] = {}


def _get_config() -> dict:
    """Load OAuth configuration from oauth_config.py (keyed by APP_ENV)."""
    return get_oauth_config()


def _build_authorization_url() -> str:
    """
    Build the IdentityServer authorization URL with PKCE and CSRF state.

    Generates a fresh verifier/challenge pair and CSRF state token for each
    unauthenticated visit, then caches the verifier server-side.
    """
    config = _get_config()

    # PKCE: code_verifier is a random 32-byte URL-safe base64 string.
    # code_challenge = BASE64URL(SHA256(verifier)).
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()

    # CSRF protection: bind this redirect to a unique, unpredictable state.
    state = _secrets.token_urlsafe(24)
    _pkce_cache[state] = verifier

    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": config["scopes"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{config['authority']}/connect/authorize?" + urllib.parse.urlencode(params)


def _exchange_code(code: str, state: str) -> dict | None:
    """
    Exchange an authorization code for a token set.

    Validates the CSRF state and uses the cached PKCE verifier.
    Returns the parsed token response dict on success, None on failure.
    """
    # Pop verifier — each state is single-use (replay protection).
    verifier = _pkce_cache.pop(state, None)
    if verifier is None:
        # Unknown or replayed state — reject.
        return None

    config = _get_config()

    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config["redirect_uri"],
        "client_id": config["client_id"],
        "code_verifier": verifier,
    }
    # Only include client_secret if configured (public clients omit it).
    if config["client_secret"]:
        payload["client_secret"] = config["client_secret"]

    try:
        resp = requests.post(
            f"{config['authority']}/connect/token",
            data=payload,
            timeout=15,
        )
        if resp.ok:
            return resp.json()
    except requests.RequestException:
        pass

    return None


def is_authenticated() -> bool:
    """Return True if the current session holds a valid OAuth token."""
    return bool(st.session_state.get("oauth_token"))


def require_auth() -> None:
    """
    Enforce OAuth authentication.  Call immediately after st.set_page_config().

    Behaviour:
    - Authenticated session  → returns immediately; app renders normally.
    - OAuth callback detected (``?code=&state=`` in URL)
                             → exchanges code for token, stores it, reruns.
    - Not authenticated      → redirects browser to the IdentityServer login
                               page and stops script execution.
    """
    params = st.query_params.to_dict()

    # -----------------------------------------------------------------------
    # OAuth callback: IdentityServer redirected back with ?code=…&state=…
    # -----------------------------------------------------------------------
    if "code" in params and "state" in params:
        token = _exchange_code(params["code"], params["state"])
        if token:
            st.session_state["oauth_token"] = token
            st.query_params.clear()
            st.rerun()
        else:
            st.error(
                "Authentication failed — the login session expired or the "
                "callback was invalid.  Please reload the page to try again."
            )
            st.stop()

    # -----------------------------------------------------------------------
    # Not authenticated → redirect to OAuth provider
    # -----------------------------------------------------------------------
    if not is_authenticated():
        auth_url = _build_authorization_url()
        safe_url = html_lib.escape(auth_url, quote=True)

        # Instant redirect via HTTP-equiv meta-refresh (no button click needed).
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={safe_url}">',
            unsafe_allow_html=True,
        )
        # Fallback visible link in case meta-refresh is blocked by the browser.
        st.markdown(
            f"Redirecting to login\u2026  "
            f"[Click here if not redirected automatically]({auth_url})"
        )
        st.stop()
