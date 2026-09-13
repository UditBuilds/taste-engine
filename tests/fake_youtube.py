"""A minimal stand-in for the YouTube Data API client.

Mirrors the chained shape the real client uses -
`service.playlistItems().insert(...).execute()` - and keeps enough state to
answer `list`, so verification can be tested without a network call. No test in
this suite touches the real API.
"""
from __future__ import annotations


class FakeResponse:
    def __init__(self, status: int):
        self.status = status


class FakeHttpError(Exception):
    """Shaped like googleapiclient.errors.HttpError for the paths we inspect."""

    def __init__(self, status: int, message: str):
        self.resp = FakeResponse(status)
        super().__init__(message)


def quota_exceeded() -> FakeHttpError:
    return FakeHttpError(403, "quotaExceeded: The request cannot be completed.")


def unauthorized() -> FakeHttpError:
    return FakeHttpError(401, "Invalid Credentials")


def transient_error(status: int, message: str = "transient failure") -> FakeHttpError:
    """A retryable-shaped failure: 409, 500, 502, 503, 504."""
    return FakeHttpError(status, message)


class _Request:
    def __init__(self, fn, kwargs):
        self._fn, self._kwargs = fn, kwargs

    def execute(self):
        return self._fn(**self._kwargs)


class _Playlists:
    def __init__(self, api):
        self.api = api

    def insert(self, **kwargs):
        return _Request(self.api._create_playlist, kwargs)

    def delete(self, **kwargs):
        return _Request(self.api._delete_playlist, kwargs)


class _PlaylistItems:
    def __init__(self, api):
        self.api = api

    def insert(self, **kwargs):
        return _Request(self.api._insert_item, kwargs)

    def list(self, **kwargs):
        return _Request(self.api._list_items, kwargs)


class FakeYouTube:
    """In-memory YouTube.

    `fail_inserts_after` makes the Nth `playlistItems.insert` raise a 403
    quotaExceeded, which is how a mid-write quota exhaustion is simulated.
    `drop_every` silently discards every Nth insert, so verification has
    something real to catch.

    `insert_errors` / `create_errors` / `delete_errors` / `list_errors` map a
    1-based physical call number to an exception to raise on that call only -
    so a retry sequence can be scripted precisely: `{1: transient_error(409)}`
    fails once then succeeds, `{1: ..., 2: ..., 3: ..., 4: ..., 5: ...}`
    exhausts all 5 attempts. Checked before `fail_inserts_after`/`drop_every`,
    so existing tests using only those are unaffected.
    """

    def __init__(
        self,
        fail_inserts_after: int | None = None,
        drop_every: int | None = None,
        insert_errors: dict[int, Exception] | None = None,
        create_errors: dict[int, Exception] | None = None,
        delete_errors: dict[int, Exception] | None = None,
        list_errors: dict[int, Exception] | None = None,
    ):
        self.playlists_store: dict[str, dict] = {}
        self.items_store: dict[str, list[str]] = {}
        self.insert_calls = 0
        self.list_calls = 0
        self.created = 0
        self.delete_calls = 0
        self.deleted: list[str] = []
        self.fail_inserts_after = fail_inserts_after
        self.drop_every = drop_every
        self.insert_errors = dict(insert_errors or {})
        self.create_errors = dict(create_errors or {})
        self.delete_errors = dict(delete_errors or {})
        self.list_errors = dict(list_errors or {})

    # --- resources ---
    def playlists(self):
        return _Playlists(self)

    def playlistItems(self):
        return _PlaylistItems(self)

    # --- implementations ---
    def _create_playlist(self, part=None, body=None):
        self.created += 1
        if self.created in self.create_errors:
            raise self.create_errors[self.created]
        pid = f"PL_fake_{self.created}"
        snippet = (body or {}).get("snippet", {})
        status = (body or {}).get("status", {})
        self.playlists_store[pid] = {
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "privacyStatus": status.get("privacyStatus"),
        }
        self.items_store[pid] = []
        return {"id": pid, "snippet": snippet, "status": status}

    def _delete_playlist(self, id=None):
        self.delete_calls += 1
        if self.delete_calls in self.delete_errors:
            raise self.delete_errors[self.delete_calls]
        self.deleted.append(id)
        self.playlists_store.pop(id, None)
        self.items_store.pop(id, None)
        return ""

    def _insert_item(self, part=None, body=None):
        self.insert_calls += 1
        if self.insert_calls in self.insert_errors:
            raise self.insert_errors[self.insert_calls]
        if (
            self.fail_inserts_after is not None
            and self.insert_calls > self.fail_inserts_after
        ):
            raise quota_exceeded()

        snippet = (body or {}).get("snippet", {})
        pid = snippet.get("playlistId")
        vid = snippet.get("resourceId", {}).get("videoId")
        if pid not in self.items_store:
            raise FakeHttpError(404, "playlistNotFound")

        dropped = self.drop_every and self.insert_calls % self.drop_every == 0
        if not dropped:
            self.items_store[pid].append(vid)
        return {"id": f"ITEM_{self.insert_calls}", "snippet": snippet}

    def _list_items(self, part=None, playlistId=None, maxResults=50, pageToken=None):
        self.list_calls += 1
        if self.list_calls in self.list_errors:
            raise self.list_errors[self.list_calls]
        items = self.items_store.get(playlistId, [])
        start = int(pageToken or 0)
        page = items[start : start + maxResults]
        response = {"items": [{"id": f"ITEM_{start + i}"} for i in range(len(page))]}
        if start + maxResults < len(items):
            response["nextPageToken"] = str(start + maxResults)
        return response
