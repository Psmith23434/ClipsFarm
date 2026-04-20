"""
twitch_api.py
Twitch Helix API client for ClipsFarm.
Handles authentication (Client Credentials), clip fetching,
game lookup, and broadcaster lookup.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from config import cfg

logger = logging.getLogger(__name__)


class TwitchAuthError(Exception):
    pass


class TwitchAPIError(Exception):
    pass


class TwitchClient:
    """
    Stateful Twitch Helix API client.
    Automatically fetches and refreshes the app access token.
    """

    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    #  Authentication                                                      #
    # ------------------------------------------------------------------ #

    def _ensure_token(self) -> None:
        """Fetch a new app access token if missing or expired."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return

        if not cfg.has_credentials():
            raise TwitchAuthError(
                "Twitch credentials not set. "
                "Please enter your Client ID and Client Secret in Settings."
            )

        resp = self._session.post(
            cfg.TWITCH_AUTH_URL,
            data={
                "client_id": cfg.TWITCH_CLIENT_ID,
                "client_secret": cfg.TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
            timeout=10,
        )

        if resp.status_code != 200:
            raise TwitchAuthError(
                f"Token request failed ({resp.status_code}): {resp.text}"
            )

        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        logger.info("Twitch access token acquired.")

    def _headers(self) -> dict:
        self._ensure_token()
        return {
            "Client-ID": cfg.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {self._access_token}",
        }

    def invalidate_token(self) -> None:
        """Force token refresh on next request (e.g. after credential change)."""
        self._access_token = None
        self._token_expires_at = 0.0

    # ------------------------------------------------------------------ #
    #  Game lookup                                                         #
    # ------------------------------------------------------------------ #

    def get_game_id(self, game_name: str) -> Optional[str]:
        """Return the Twitch game ID for a given game name, or None."""
        resp = self._session.get(
            f"{cfg.TWITCH_API_BASE}/games",
            headers=self._headers(),
            params={"name": game_name},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0]["id"] if data else None

    def get_game_name(self, game_id: str) -> Optional[str]:
        """Return the game name for a given game ID, or None."""
        resp = self._session.get(
            f"{cfg.TWITCH_API_BASE}/games",
            headers=self._headers(),
            params={"id": game_id},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0]["name"] if data else None

    # ------------------------------------------------------------------ #
    #  Broadcaster lookup                                                  #
    # ------------------------------------------------------------------ #

    def get_broadcaster_id(self, login: str) -> Optional[str]:
        """Return the broadcaster ID for a given login name, or None."""
        resp = self._session.get(
            f"{cfg.TWITCH_API_BASE}/users",
            headers=self._headers(),
            params={"login": login.strip().lower()},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0]["id"] if data else None

    def get_broadcaster_info(self, login: str) -> Optional[dict]:
        """Return full broadcaster info dict for a login name, or None."""
        resp = self._session.get(
            f"{cfg.TWITCH_API_BASE}/users",
            headers=self._headers(),
            params={"login": login.strip().lower()},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0] if data else None

    # ------------------------------------------------------------------ #
    #  Clip fetching                                                       #
    # ------------------------------------------------------------------ #

    def get_clips(
        self,
        *,
        game_id: Optional[str] = None,
        broadcaster_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        max_results: int = 100,
        min_views: int = 0,
        language: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch existing clips from Twitch. Paginates automatically.

        Args:
            game_id:        Filter by game (e.g. CS2 ID).
            broadcaster_id: Filter by broadcaster.
            started_at:     Only clips created after this UTC datetime.
            ended_at:       Only clips created before this UTC datetime.
            max_results:    Maximum total clips to return (paginates until reached).
            min_views:      Skip clips below this view count.
            language:       ISO 639-1 language code, e.g. 'en', 'de'.

        Returns:
            List of clip dicts with normalised fields.
        """
        if not game_id and not broadcaster_id:
            raise ValueError("Provide at least one of: game_id, broadcaster_id")

        params: dict = {"first": min(100, max_results)}

        if game_id:
            params["game_id"] = game_id
        if broadcaster_id:
            params["broadcaster_id"] = broadcaster_id
        if started_at:
            params["started_at"] = started_at.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        if ended_at:
            params["ended_at"] = ended_at.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        if language:
            params["language"] = language

        clips: list[dict] = []
        cursor: Optional[str] = None
        fetched = 0

        while fetched < max_results:
            if cursor:
                params["after"] = cursor

            resp = self._session.get(
                f"{cfg.TWITCH_API_BASE}/clips",
                headers=self._headers(),
                params=params,
                timeout=15,
            )

            if resp.status_code == 401:
                self.invalidate_token()
                self._ensure_token()
                continue

            resp.raise_for_status()
            payload = resp.json()
            page_data: list[dict] = payload.get("data", [])

            if not page_data:
                break

            for raw in page_data:
                if raw.get("view_count", 0) < min_views:
                    continue
                clips.append(self._normalise_clip(raw))
                fetched += 1
                if fetched >= max_results:
                    break

            cursor = payload.get("pagination", {}).get("cursor")
            if not cursor:
                break

        logger.info("Fetched %d clips.", len(clips))
        return clips

    # ------------------------------------------------------------------ #
    #  Convenience presets                                                 #
    # ------------------------------------------------------------------ #

    def get_top_game_clips(
        self,
        game_id: Optional[str] = None,
        days: int = 7,
        max_results: int = 100,
        min_views: int = 0,
        language: Optional[str] = None,
    ) -> list[dict]:
        """Shortcut: top clips for a game over the last N days."""
        game_id = game_id or cfg.DEFAULT_GAME_ID
        started_at = datetime.now(timezone.utc) - timedelta(days=days)
        return self.get_clips(
            game_id=game_id,
            started_at=started_at,
            max_results=max_results,
            min_views=min_views,
            language=language,
        )

    def get_broadcaster_clips(
        self,
        broadcaster_login: str,
        days: int = 7,
        max_results: int = 50,
        min_views: int = 0,
    ) -> list[dict]:
        """Shortcut: top clips for a single broadcaster over the last N days."""
        broadcaster_id = self.get_broadcaster_id(broadcaster_login)
        if not broadcaster_id:
            logger.warning("Broadcaster not found: %s", broadcaster_login)
            return []
        started_at = datetime.now(timezone.utc) - timedelta(days=days)
        return self.get_clips(
            broadcaster_id=broadcaster_id,
            started_at=started_at,
            max_results=max_results,
            min_views=min_views,
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalise_clip(raw: dict) -> dict:
        """
        Flatten the raw Twitch API clip dict into a clean, consistent
        structure used throughout the app.
        """
        return {
            "clip_id":          raw.get("id", ""),
            "url":              raw.get("url", ""),
            "embed_url":        raw.get("embed_url", ""),
            "thumbnail_url":    raw.get("thumbnail_url", ""),
            "title":            raw.get("title", ""),
            "broadcaster_id":   raw.get("broadcaster_id", ""),
            "broadcaster_name": raw.get("broadcaster_name", ""),
            "creator_id":       raw.get("creator_id", ""),
            "creator_name":     raw.get("creator_name", ""),
            "game_id":          raw.get("game_id", ""),
            "language":         raw.get("language", ""),
            "view_count":       raw.get("view_count", 0),
            "duration":         raw.get("duration", 0.0),
            "vod_offset":       raw.get("vod_offset"),
            "is_featured":      raw.get("is_featured", False),
            "created_at":       raw.get("created_at", ""),
        }


# Module-level singleton
twitch = TwitchClient()
