#!/bin/sh
set -e

mkdir -p /app/.streamlit

# Streamlit requires secrets.toml to exist; OAuth config is in oauth_config.py.
if [ ! -f /app/.streamlit/secrets.toml ]; then
    touch /app/.streamlit/secrets.toml
fi

exec streamlit run app.py \
    --server.port=8080 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
