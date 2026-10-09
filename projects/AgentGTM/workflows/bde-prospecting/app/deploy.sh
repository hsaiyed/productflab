#!/usr/bin/env bash
# Deploy the web app to Google Cloud Run. See docs/deploy-web-app.md for the one-time setup.
#   SHEET_ID=<spreadsheet id> REGION=us-central1 ./app/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${SHEET_ID:?set SHEET_ID to the Google Sheet id}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-agentgtm-app}"

# Playbooks live at the project level; copy them into the build context.
rm -rf playbooks && cp -r ../../playbooks ./playbooks
trap 'rm -rf playbooks' EXIT

SECRETS="/app/.streamlit/secrets.toml=agentgtm-streamlit-secrets:latest,/secrets/sa/key.json=agentgtm-sa-key:latest"
if gcloud secrets describe anthropic-api-key >/dev/null 2>&1; then
  SECRETS="$SECRETS,ANTHROPIC_API_KEY=anthropic-api-key:latest"
fi

# --allow-unauthenticated lets the page load; the app itself requires Google sign-in
# and only shows data to emails listed in the config.
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --session-affinity \
  --min-instances 0 --max-instances 2 \
  --memory 1Gi \
  --set-env-vars "AGENTGTM_STORE=sheets:${SHEET_ID},GOOGLE_SERVICE_ACCOUNT_FILE=/secrets/sa/key.json" \
  --set-secrets "$SECRETS"
