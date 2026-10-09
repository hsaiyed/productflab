# Web app: Google sign-in and deployment

Founders and the owner sign in with their Google account. Access is decided by email:

| Who | Where their email goes | What they see |
| --- | --- | --- |
| Owner | `config/bdes.toml` → `[owner] emails` | Everything: pipeline, BDE quality, review queue, agent activity, every founder page, ask the agent |
| Founder | `playbooks/<startup>.toml` → `founder_emails` | Only their startup: today's invites with notes, and buttons to record sent / accepted / replied / meeting / not a fit / don't contact |
| Anyone else | — | "Doesn't have access" |

Any Google account works (Gmail or Google Workspace). Emails are matched case-insensitively and must be verified by Google. Every action is re-checked on the server (`src/bde_prospecting/access.py`), so a founder can never see or change another startup's data. If this repo is public, remember the emails in the config are public too.

## Try it locally first (no Google setup)

```sh
pip install -e '.[app]'
python app/demo.py owner      # or: daxa, fastn, autonomops, architecto, stranger
```

This uses a copy of the demo sheet and a fake sign-in. The app refuses fake sign-in with a real Google Sheet.

## One-time setup

### 1. Google sign-in (OAuth client)

In [Google Cloud Console](https://console.cloud.google.com/), in the project that has the Sheets service account:

1. **APIs & Services → OAuth consent screen.** User type **External** (founders use their own Google accounts). App name "AgentGTM", your support email. Scopes: only `openid`, `email`, `profile`. Because these are basic scopes, you can set publishing status to **In production** without Google's review. (In "Testing" mode you'd have to add every founder as a test user and they'd be signed out weekly.)
2. **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application.**
   Authorized redirect URIs:
   - `http://localhost:8501/oauth2callback` (local testing)
   - `https://<your Cloud Run URL>/oauth2callback` (add after the first deploy; see step 4)
3. Copy the client ID and secret into a copy of `app/secrets.example.toml`, with a long random `cookie_secret`.

To test Google sign-in locally: save it as `.streamlit/secrets.toml` in this folder (git-ignored), then
`AGENTGTM_STORE=sheets:<id> GOOGLE_SERVICE_ACCOUNT_FILE=key.json streamlit run app/streamlit_app.py`.

### 2. Secrets in Secret Manager

```sh
gcloud services enable run.googleapis.com secretmanager.googleapis.com cloudbuild.googleapis.com
gcloud secrets create agentgtm-streamlit-secrets --data-file=secrets.toml       # with the Cloud Run redirect_uri
gcloud secrets create agentgtm-sa-key --data-file=/path/to/service-account-key.json
printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-   # optional: "Ask the agent"
```

Give the Cloud Run runtime service account the **Secret Manager Secret Accessor** role on these secrets.

### 3. Add the emails

Put your email in `config/bdes.toml` `[owner] emails`, and each founder's in their playbook's `founder_emails`. Commit, then deploy.

### 4. Deploy

```sh
SHEET_ID=<spreadsheet id> ./app/deploy.sh
```

The first deploy prints the service URL. Put `https://<that URL>/oauth2callback` into the OAuth client's redirect URIs and into the `redirect_uri` in the secret (`gcloud secrets versions add agentgtm-streamlit-secrets --data-file=secrets.toml`), then run `deploy.sh` again. Optionally map a custom domain such as `gtm.yourdomain.com` and use that URL instead.

The service scales to zero when unused, so cost should be close to nothing at this usage.

## Adding or removing a founder

Edit `founder_emails` in their playbook and redeploy. Removing an email takes effect on the next deploy; their Google sign-in still works but shows "doesn't have access".
