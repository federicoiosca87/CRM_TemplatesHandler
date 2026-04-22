#!/bin/sh
set -e

mkdir -p /app/.streamlit

if [ ! -f /app/.streamlit/secrets.toml ]; then
    cat > /app/.streamlit/secrets.toml << SECRETS
[oauth]
authority      = "${OAUTH_AUTHORITY}"
client_id      = "${OAUTH_CLIENT_ID}"
client_secret  = "${OAUTH_CLIENT_SECRET}"
scopes         = "${OAUTH_SCOPES}"
redirect_uri   = "${OAUTH_REDIRECT_URI}"
SECRETS
fi

exec streamlit run app.py \
    --server.port=8080 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
