"""
config.py
Central configuration loader for ClipsFarm.
Reads from .env file and provides a singleton Config object
used across all modules.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


class Config:
    """Singleton-style config object. Import and use `cfg` directly."""

    # ------------------------------------------------------------------ #
    #  Twitch credentials                                                  #
    # ------------------------------------------------------------------ #
    TWITCH_CLIENT_ID: str = os.getenv("TWITCH_CLIENT_ID", "")
    TWITCH_CLIENT_SECRET: str = os.getenv("TWITCH_CLIENT_SECRET", "")

    # Twitch API base URL
    TWITCH_API_BASE: str = "https://api.twitch.tv/helix"
    TWITCH_AUTH_URL: str = "https://id.twitch.tv/oauth2/token"

    # ------------------------------------------------------------------ #
    #  Default fetch settings                                              #
    # ------------------------------------------------------------------ #
    # CS2 game ID on Twitch (can be overridden in .env)
    DEFAULT_GAME_ID: str = os.getenv("DEFAULT_GAME_ID", "1659186957")

    # Maximum clips per single API page (Twitch max = 100)
    MAX_CLIPS_PER_FETCH: int = int(os.getenv("MAX_CLIPS_PER_FETCH", "100"))

    # Minimum view count to include a clip
    MIN_VIEW_COUNT: int = int(os.getenv("MIN_VIEW_COUNT", "50"))

    # Default time window in days for "recent" presets
    DEFAULT_TIME_WINDOW_DAYS: int = int(os.getenv("DEFAULT_TIME_WINDOW_DAYS", "7"))

    # ------------------------------------------------------------------ #
    #  Auto-refresh                                                        #
    # ------------------------------------------------------------------ #
    AUTO_REFRESH_INTERVAL_MINUTES: int = int(
        os.getenv("AUTO_REFRESH_INTERVAL_MINUTES", "60")
    )
    AUTO_REFRESH_ENABLED: bool = (
        os.getenv("AUTO_REFRESH_ENABLED", "false").lower() == "true"
    )

    # ------------------------------------------------------------------ #
    #  Database                                                            #
    # ------------------------------------------------------------------ #
    DB_PATH: str = os.getenv(
        "DB_PATH",
        str(Path(__file__).parent / "clips.db")
    )

    # ------------------------------------------------------------------ #
    #  UI / appearance                                                     #
    # ------------------------------------------------------------------ #
    DARK_MODE: bool = os.getenv("DARK_MODE", "true").lower() == "true"
    APP_NAME: str = "ClipsFarm"
    APP_VERSION: str = "0.1.0"
    WINDOW_WIDTH: int = 1400
    WINDOW_HEIGHT: int = 860

    # ------------------------------------------------------------------ #
    #  Scoring weights (used to rank clips beyond raw view count)          #
    # ------------------------------------------------------------------ #
    # Final score = views * VIEW_WEIGHT + recency_bonus * RECENCY_WEIGHT
    # recency_bonus = max(0, 7 - age_in_days) scaled 0-1
    SCORE_VIEW_WEIGHT: float = float(os.getenv("SCORE_VIEW_WEIGHT", "1.0"))
    SCORE_RECENCY_WEIGHT: float = float(os.getenv("SCORE_RECENCY_WEIGHT", "0.3"))

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    @classmethod
    def has_credentials(cls) -> bool:
        """Returns True if both Twitch credentials are set."""
        return bool(cls.TWITCH_CLIENT_ID and cls.TWITCH_CLIENT_SECRET)

    @classmethod
    def reload(cls) -> None:
        """Re-read .env from disk (useful after user saves credentials in GUI)."""
        load_dotenv(dotenv_path=_ENV_PATH, override=True)
        cls.TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
        cls.TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
        cls.DEFAULT_GAME_ID = os.getenv("DEFAULT_GAME_ID", "1659186957")
        cls.MAX_CLIPS_PER_FETCH = int(os.getenv("MAX_CLIPS_PER_FETCH", "100"))
        cls.MIN_VIEW_COUNT = int(os.getenv("MIN_VIEW_COUNT", "50"))
        cls.AUTO_REFRESH_INTERVAL_MINUTES = int(
            os.getenv("AUTO_REFRESH_INTERVAL_MINUTES", "60")
        )
        cls.AUTO_REFRESH_ENABLED = (
            os.getenv("AUTO_REFRESH_ENABLED", "false").lower() == "true"
        )

    @classmethod
    def save_credentials(cls, client_id: str, client_secret: str) -> None:
        """
        Write/update TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET in .env
        and reload config. Called from the credentials dialog in the GUI.
        """
        env_lines: list[str] = []

        # Read existing .env if present
        if _ENV_PATH.exists():
            env_lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

        def _set_key(lines: list[str], key: str, value: str) -> list[str]:
            """Update or append a key=value line."""
            updated = False
            result = []
            for line in lines:
                if line.startswith(f"{key}="):
                    result.append(f"{key}={value}")
                    updated = True
                else:
                    result.append(line)
            if not updated:
                result.append(f"{key}={value}")
            return result

        env_lines = _set_key(env_lines, "TWITCH_CLIENT_ID", client_id)
        env_lines = _set_key(env_lines, "TWITCH_CLIENT_SECRET", client_secret)

        _ENV_PATH.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        cls.reload()


# Module-level singleton — import this everywhere
cfg = Config()
