# Web app for founders and the owner. Build from this folder:
#   docker build -t agentgtm-app .
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e '.[app]'
COPY config ./config
COPY app ./app
# Playbooks live at the project level; copy them in at build time (see docs/deploy-web-app.md).
COPY playbooks ./playbooks

ENV AGENTGTM_PLAYBOOK_DIR=/app/playbooks \
    STREAMLIT_CLIENT_TOOLBAR_MODE=viewer \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true
# Google sign-in settings are read from /app/.streamlit/secrets.toml (mounted from Secret Manager).

EXPOSE 8080
CMD ["sh", "-c", "streamlit run app/streamlit_app.py --server.port ${PORT:-8080} --server.address 0.0.0.0"]
