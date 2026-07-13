"""GitHub relay.

- Polls the watched repo for releases and announces new ones in the
  releases channel. Edited releases on GitHub are synced by editing the
  original announcement embed in place.
- /release shows the latest release.
- /issue looks up an issue or PR by number.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

if TYPE_CHECKING:
    from ..client import Sodutod

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


class GitHubCog(commands.Cog, name="GitHub"):
    def __init__(self, bot: "Sodutod") -> None:
        self.bot = bot
        self.config = bot.config
        self.session: aiohttp.ClientSession | None = None
        self.state_path = Path(self.config.state_dir) / "github_state.json"

    async def cog_load(self) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "sodutod",
        }
        if self.config.github_token:
            headers["Authorization"] = f"Bearer {self.config.github_token}"
        self.session = aiohttp.ClientSession(headers=headers)

        self.poll_releases.change_interval(seconds=self.config.release_poll_seconds)
        self.poll_releases.start()

    async def cog_unload(self) -> None:
        self.poll_releases.cancel()
        if self.session is not None:
            await self.session.close()

    async def _fetch_json(self, path: str) -> Any:
        assert self.session is not None
        async with self.session.get(GITHUB_API + path, raise_for_status=True) as resp:
            return await resp.json()

    # -- release announcements ------------------------------------------

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state))

    @staticmethod
    def _release_digest(release: dict) -> str:
        """Fingerprint of the announced content, to detect edits on GitHub."""
        payload = "\x1f".join(
            str(release.get(key))
            for key in ("tag_name", "name", "body", "prerelease")
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    @tasks.loop(seconds=300)
    async def poll_releases(self) -> None:
        try:
            releases = await self._fetch_json(
                f"/repos/{self.config.github_repo}/releases?per_page=10"
            )
        except Exception:
            log.exception("Failed to fetch releases")
            return

        releases = [r for r in releases if not r.get("draft")]
        if not releases:
            return

        state = self._load_state()
        known: dict = state.setdefault("releases", {})
        # First run: record current releases without replaying history.
        first_run = not state.get("seeded")

        for release in sorted(releases, key=lambda r: r["id"]):
            key = str(release["id"])
            digest = self._release_digest(release)
            entry = known.get(key)
            if entry is None:
                message_id = None if first_run else await self._announce(release)
                known[key] = {"message_id": message_id, "digest": digest}
                self._save_state(state)
            elif entry.get("digest") != digest:
                await self._sync_edited(release, entry)
                entry["digest"] = digest
                self._save_state(state)

        if first_run:
            state["seeded"] = True
            self._save_state(state)
            await self.bot.telemetry(
                f"📦 First run — recorded {len(releases)} existing releases of "
                f"`{self.config.github_repo}` without announcing; only releases "
                "published from now on are announced."
            )

    @poll_releases.before_loop
    async def _wait_for_ready(self) -> None:
        await self.bot.wait_until_ready()

    async def _announce(self, release: dict) -> int | None:
        """Post a release announcement; returns the message id for edit-sync."""
        channel = self.bot.get_channel(self.config.channel_releases_id)
        if not isinstance(channel, discord.TextChannel):
            log.warning("Releases channel not found; skipping announcement")
            return None
        message = await channel.send(embed=self._release_embed(release))
        await self.bot.telemetry(
            f"📦 Announced release `{release.get('tag_name')}` in {channel.mention}"
        )
        return message.id

    async def _sync_edited(self, release: dict, entry: dict) -> None:
        """Reflect a release edited on GitHub into its original embed."""
        message_id = entry.get("message_id")
        channel = self.bot.get_channel(self.config.channel_releases_id)
        if message_id is None or not isinstance(channel, discord.TextChannel):
            return
        tag = release.get("tag_name")
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=self._release_embed(release))
            await self.bot.telemetry(f"✏️ Synced edited release `{tag}`")
        except discord.NotFound:
            # The announcement was deleted on Discord — assume intentionally.
            log.warning("Announcement for %s was deleted; not reposting", tag)
        except discord.DiscordException:
            log.exception("Failed to sync edited release %s", tag)

    def _release_embed(self, release: dict) -> discord.Embed:
        body = (release.get("body") or "").strip()
        if len(body) > 1500:
            body = body[:1500] + "…"
        prerelease = bool(release.get("prerelease"))
        kind = "Pre-release" if prerelease else "Release"
        embed = discord.Embed(
            title=f"📦 {kind}: {release.get('name') or release.get('tag_name')}",
            url=release.get("html_url"),
            description=body or "*No release notes.*",
            color=discord.Color.orange() if prerelease else discord.Color.green(),
        )
        embed.set_footer(text=f"{self.config.github_repo} · {release.get('tag_name')}")
        return embed

    # -- slash commands --------------------------------------------------

    @app_commands.command(name="release", description="Show the latest Soduto release.")
    async def release(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            release = await self._fetch_json(
                f"/repos/{self.config.github_repo}/releases/latest"
            )
        except Exception:
            log.exception("Failed to fetch latest release")
            await interaction.followup.send("Couldn't reach GitHub — try again later.")
            return
        await interaction.followup.send(embed=self._release_embed(release))

    @app_commands.command(
        name="issue", description="Look up a GitHub issue or PR by number."
    )
    @app_commands.describe(number="Issue or pull request number")
    async def issue(self, interaction: discord.Interaction, number: int) -> None:
        await interaction.response.defer()
        try:
            data = await self._fetch_json(
                f"/repos/{self.config.github_repo}/issues/{number}"
            )
        except aiohttp.ClientResponseError as error:
            if error.status == 404:
                await interaction.followup.send(
                    f"No issue or PR #{number} in `{self.config.github_repo}`."
                )
            else:
                await interaction.followup.send(
                    "GitHub returned an error — try again later."
                )
            return
        except Exception:
            log.exception("Failed to fetch issue #%s", number)
            await interaction.followup.send("Couldn't reach GitHub — try again later.")
            return

        is_pr = "pull_request" in data
        state = data.get("state", "unknown")
        embed = discord.Embed(
            title=f"{'PR' if is_pr else 'Issue'} #{number}: {data.get('title')}",
            url=data.get("html_url"),
            description=(data.get("body") or "")[:500] or None,
            color=discord.Color.green()
            if state == "open"
            else discord.Color.dark_grey(),
        )
        embed.add_field(name="State", value=state, inline=True)
        labels = ", ".join(label["name"] for label in data.get("labels", []))
        if labels:
            embed.add_field(name="Labels", value=labels, inline=True)
        await interaction.followup.send(embed=embed)
