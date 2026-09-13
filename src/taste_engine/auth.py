"""OAuth for Phase 4. Reading needs an API key; writing needs a user.

`videos.list` reads public data and takes an API key, which is why Phase 2
never needed a consent screen. Creating a playlist acts *as the account
holder*, so it needs OAuth and the full `youtube` scope -
`youtube.readonly` cannot create anything.

There is deliberately **no fallback to the API key**. A write path that
silently degrades to an unauthenticated client would fail deep inside the
first insert with an opaque 401; failing here, by name, is better.

First run opens a browser. Because the Cloud project is published but not
verified by Google, an "unverified app" interstitial appears - Advanced ->
Go to taste-engine (unsafe). That warning is about Google not having reviewed
the app, not about the app doing anything unusual; it is your own client
talking to your own account. Published (not Testing) means the refresh token
does not expire after seven days.
"""
from __future__ import annotations

from pathlib import Path

from . import config

API_SERVICE = "youtube"
API_VERSION = "v3"


class MissingCredentials(RuntimeError):
    """The OAuth client file is absent. Says which file and where to put it."""


def _credentials_help(path: Path) -> str:
    return (
        f"OAuth client not found at {path}\n\n"
        "Phase 4 writes to your YouTube account, so it needs OAuth - an API key\n"
        "cannot create playlists, and this will not fall back to one.\n\n"
        "  1. https://console.cloud.google.com/apis/credentials\n"
        "  2. Create credentials -> OAuth client ID -> Desktop app\n"
        f"  3. Download the JSON and save it as:  {path}\n\n"
        "It is gitignored. On first run a browser opens and Google shows an\n"
        "'unverified app' warning: Advanced -> Go to taste-engine (unsafe)."
    )


def load_credentials(
    credentials_path: Path | None = None,
    token_path: Path | None = None,
    interactive: bool = True,
):
    """Return usable OAuth credentials, refreshing or re-authorising as needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials_path = credentials_path or config.CREDENTIALS_PATH
    token_path = token_path or config.TOKEN_PATH
    scopes = config.OAUTH_SCOPES

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except (ValueError, KeyError):
            creds = None  # corrupt or written for different scopes

    # A token saved under a narrower scope cannot write; force a re-consent.
    if creds and not creds.has_scopes(scopes):
        creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(creds, token_path)
            return creds
        except Exception:  # noqa: BLE001 - revoked or rotated; fall through
            creds = None

    if not credentials_path.exists():
        raise MissingCredentials(_credentials_help(credentials_path))
    if not interactive:
        raise MissingCredentials(
            f"No valid token at {token_path} and interactive consent is disabled. "
            "Run `taste-engine write` once from a terminal to authorise."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes)
    creds = flow.run_local_server(port=0)
    _save(creds, token_path)
    return creds


def _save(creds, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    try:  # best effort; no-op on Windows
        token_path.chmod(0o600)
    except OSError:
        pass


def build_service(credentials=None, **kwargs):
    """An authorised YouTube Data API client."""
    from googleapiclient.discovery import build

    return build(
        API_SERVICE,
        API_VERSION,
        credentials=credentials or load_credentials(**kwargs),
        cache_discovery=False,
    )


def authorised_channel(service) -> dict:
    """Whose account are we about to write to? Confirms the token is live.

    `channels.list(mine=True)` costs 1 unit and is worth it: writing 50 tracks
    to the wrong account is a 2,550-unit mistake.
    """
    response = service.channels().list(part="snippet", mine=True).execute()
    items = response.get("items", [])
    if not items:
        return {"id": None, "title": "(no channel on this account)"}
    return {
        "id": items[0]["id"],
        "title": items[0]["snippet"].get("title", "(untitled)"),
    }
