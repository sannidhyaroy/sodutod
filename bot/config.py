"""Environment-based configuration for sodutod.

Discord objects are referenced by ID only, and variable names describe
purpose (rules channel, member role, ...) rather than any particular
channel/role naming scheme, so the server can be renamed or rethemed
freely.
"""

import os
from dataclasses import dataclass


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_int(name: str) -> int:
    return int(_env(name))


@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int

    # Role given on join, and the role it is swapped for on verification.
    role_unverified_id: int
    role_member_id: int

    # Channel hosting the rules + verification button.
    channel_rules_id: int
    # Channel for welcome messages (used when WELCOME_MODE=roster or public).
    channel_welcome_id: int
    # Channel for release announcements.
    channel_releases_id: int
    # Channel for the bot's operational telemetry.
    channel_telemetry_id: int

    github_repo: str
    github_token: str | None
    release_poll_seconds: int

    state_dir: str

    # Markdown file the bot posts into the rules channel via /post-rules.
    rules_path: str

    # How to greet new members: "roster" (default — exactly one welcome
    # message in the welcome channel mentioning everyone not yet verified;
    # reposted on join pinging only the newcomer, silently edited as members
    # verify or leave, deleted once empty), "dm" (personal message),
    # "public" (one embed per join), or "off".
    welcome_mode: str

    # Telemetry verbosity: "verbose" (default) mirrors every bot action to
    # the telemetry channel (joins, roster updates, DMs); "normal" posts
    # only significant events (verifications, announcements,
    # misconfigurations). Verbose events go to the process log either way.
    telemetry_level: str

    # Presence shown on the bot's profile. activity_type is one of
    # "playing", "streaming", "listening", "watching", "competing" or
    # "custom"; activity_url is only used for "streaming" (must be a
    # Twitch/YouTube URL for Discord to show the purple streaming status).
    activity_type: str
    activity_text: str
    activity_url: str | None

    # Commit SHA of the running build, baked into the Docker image by CI
    # (BOT_GIT_SHA); "dev" for local runs. Used for the startup update
    # announcement in the telemetry channel.
    git_sha: str
    # Repo the bot's own source lives in, for compare links between builds.
    bot_source_repo: str

    @classmethod
    def from_env(cls) -> "Config":
        welcome_mode = os.environ.get("WELCOME_MODE", "roster").strip().lower()
        if welcome_mode not in ("roster", "dm", "public", "off"):
            raise RuntimeError(
                "WELCOME_MODE must be 'roster', 'dm', 'public' or 'off', "
                f"got {welcome_mode!r}"
            )
        telemetry_level = os.environ.get("TELEMETRY_LEVEL", "verbose").strip().lower()
        if telemetry_level not in ("verbose", "normal"):
            raise RuntimeError(
                f"TELEMETRY_LEVEL must be 'verbose' or 'normal', got {telemetry_level!r}"
            )
        activity_type = os.environ.get("ACTIVITY_TYPE", "listening").strip().lower()
        if activity_type not in (
            "playing", "streaming", "listening", "watching", "competing", "custom"
        ):
            raise RuntimeError(
                "ACTIVITY_TYPE must be one of playing, streaming, listening, "
                f"watching, competing, custom — got {activity_type!r}"
            )
        return cls(
            token=_env("DISCORD_TOKEN"),
            guild_id=_env_int("GUILD_ID"),
            role_unverified_id=_env_int("ROLE_UNVERIFIED_ID"),
            role_member_id=_env_int("ROLE_MEMBER_ID"),
            channel_rules_id=_env_int("CHANNEL_RULES_ID"),
            channel_welcome_id=_env_int("CHANNEL_WELCOME_ID"),
            channel_releases_id=_env_int("CHANNEL_RELEASES_ID"),
            channel_telemetry_id=_env_int("CHANNEL_TELEMETRY_ID"),
            github_repo=os.environ.get("GITHUB_REPO", "sannidhyaroy/Soduto"),
            github_token=os.environ.get("GITHUB_TOKEN", "").strip() or None,
            release_poll_seconds=int(os.environ.get("RELEASE_POLL_SECONDS", "300")),
            state_dir=os.environ.get("STATE_DIR", "./data"),
            rules_path=os.environ.get("RULES_PATH", "./rules.md"),
            welcome_mode=welcome_mode,
            telemetry_level=telemetry_level,
            activity_type=activity_type,
            activity_text=os.environ.get("ACTIVITY_TEXT", "port 1716").strip(),
            activity_url=os.environ.get("ACTIVITY_URL", "").strip() or None,
            git_sha=os.environ.get("BOT_GIT_SHA", "").strip() or "dev",
            bot_source_repo=os.environ.get(
                "BOT_SOURCE_REPO", "sannidhyaroy/sodutod"
            ).strip(),
        )
