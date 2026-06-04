# YouTube API OAuth Setup

MoneyPrinterV2 uses browser automation for upload, but channel performance analysis should use the official YouTube APIs.

## APIs

Enable these in the same Google Cloud project:

- YouTube Data API v3
- YouTube Analytics API

## OAuth client

Create an OAuth client in Google Cloud Console:

1. APIs & Services → OAuth consent screen
   - User type: External is fine for a personal/test project.
   - Add the Google account that owns/has access to the configured YouTube channel as a test user if the app is in Testing mode.
2. APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - Download the JSON.
3. Save the downloaded file here:

```text
/opt/data/MoneyPrinterV2/secrets/youtube_oauth_client_secret.json
```

Do not commit this file. `secrets/` is gitignored.

## Scopes

The setup script requests read-only scopes only:

```text
https://www.googleapis.com/auth/youtube.readonly
https://www.googleapis.com/auth/yt-analytics.readonly
```

No upload/delete scope is requested for analytics collection.

## First authorization

From the repo root:

```bash
cd /opt/data/MoneyPrinterV2
. venv/bin/activate
python -m pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
PYTHONPATH=src python scripts/setup_youtube_oauth.py
```

The script opens a local OAuth browser flow and saves the refresh token to:

```text
/opt/data/MoneyPrinterV2/secrets/youtube_oauth_token.json
```

If the browser does not open automatically, copy the printed URL into the logged-in Firefox profile used for the YouTube channel. The script verifies the authorized channel is:

```text
`YOUTUBE_CHANNEL_NAME` / `YOUTUBE_CHANNEL_ID`
```

If the wrong Google/brand channel is authorized:

```bash
rm -f /opt/data/MoneyPrinterV2/secrets/youtube_oauth_token.json
PYTHONPATH=src python scripts/setup_youtube_oauth.py
```

## Smoke test

After OAuth succeeds:

```bash
cd /opt/data/MoneyPrinterV2
PYTHONPATH=src venv/bin/python scripts/check_youtube_api_auth.py
```

This checks:

- token exists and is refreshable
- Data API can read the channel
- Analytics API can run a 7-day read-only report

## Notes

- Keep upload automation on Selenium for now.
- Use YouTube Data API + Analytics API for metrics and reporting.
- Reporting API is not needed for the first implementation; it is better for later bulk/warehouse-style reporting.
