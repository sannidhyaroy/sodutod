"""Bot client and entry point."""

import json
import logging
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from .config import Config

log = logging.getLogger(__name__)


def _build_activity(config: Config) -> discord.BaseActivity | None:
    if not config.activity_text:
        return None
    if config.activity_type == "streaming":
        return discord.Streaming(
            name=config.activity_text,
            url=config.activity_url or "https://www.twitch.tv/directory",
        )
    if config.activity_type == "custom":
        return discord.CustomActivity(name=config.activity_text)
    return discord.Activity(
        type=getattr(discord.ActivityType, config.activity_type),
        name=config.activity_text,
    )


class Sodutod(commands.Bot):
    """Onboarding, verification, and GitHub relay for the home server."""

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True  # required for on_member_join and role management
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            activity=_build_activity(config),
        )
        self.config = config
        self._version_announced = False

    async def setup_hook(self) -> None:
        from .cogs.github import GitHubCog
        from .cogs.onboarding import OnboardingCog, VerifyView

        await self.add_cog(OnboardingCog(self))
        await self.add_cog(GitHubCog(self))

        # Re-register the persistent verification button so it keeps working
        # across restarts.
        self.add_view(VerifyView(self))

        # Global command sync: guild-scoped commands would appear instantly,
        # but only globally synced commands light up the {/} "supports
        # commands" badge and the Commands list on the bot's profile.
        # Propagation after changes can take up to an hour, which is fine
        # for a single-guild bot with a stable command set. The guild sync
        # with cleared commands removes stale guild-scoped copies from
        # earlier versions that would otherwise duplicate every command.
        guild = discord.Object(id=self.config.guild_id)
        self.tree.clear_commands(guild=guild)
        await self.tree.sync(guild=guild)
        await self.tree.sync()

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        # on_ready also fires on gateway reconnects; announce only once per
        # process.
        if not self._version_announced:
            self._version_announced = True
            await self._announce_version()

    @staticmethod
    def _short(sha: str) -> str:
        return sha if sha == "dev" else sha[:7]

    async def _announce_version(self) -> None:
        """Report which build is running, and whether it changed.

        The running build's commit SHA (baked into the image by CI) is
        compared against the one recorded in the state volume: an update
        announces old -> new with a compare link, a restart of the same
        build is a verbose-level event.
        """
        sha = self.config.git_sha
        path = Path(self.config.state_dir) / "version_state.json"
        previous = None
        try:
            previous = json.loads(path.read_text()).get("git_sha")
        except (OSError, ValueError):
            pass

        if previous == sha:
            await self.telemetry(
                f"🔄 Restarted — still running build `{self._short(sha)}`",
                verbose=True,
            )
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"git_sha": sha}))
        if previous is None:
            await self.telemetry(f"🚀 Running build `{self._short(sha)}`")
        elif "dev" in (sha, previous):
            await self.telemetry(
                f"⬆️ Updated: `{self._short(previous)}` → `{self._short(sha)}`"
            )
        else:
            await self.telemetry(
                f"⬆️ Updated: `{self._short(previous)}` → `{self._short(sha)}` — "
                f"<https://github.com/{self.config.bot_source_repo}/compare/"
                f"{previous}...{sha}>"
            )

    async def telemetry(self, message: str, *, verbose: bool = False) -> None:
        """Post an operational event to the telemetry channel. Best effort.

        Events marked ``verbose`` are only posted to Discord when
        ``TELEMETRY_LEVEL=verbose``; they go to the process log regardless.
        """
        log.info("telemetry: %s", message)
        if verbose and self.config.telemetry_level != "verbose":
            return
        try:
            channel = self.get_channel(self.config.channel_telemetry_id)
            if channel is None:
                channel = await self.fetch_channel(self.config.channel_telemetry_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await channel.send(message)
        except discord.DiscordException:
            log.exception("Failed to post to the telemetry channel")


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    config = Config.from_env()
    bot = Sodutod(config)
    bot.run(config.token, log_handler=None)
