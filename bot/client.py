"""Bot client and entry point."""

import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from .config import Config

log = logging.getLogger(__name__)


class Sodutod(commands.Bot):
    """Onboarding, verification, and GitHub relay for the home server."""

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.members = True  # required for on_member_join and role management
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = config

    async def setup_hook(self) -> None:
        from .cogs.github import GitHubCog
        from .cogs.onboarding import OnboardingCog, VerifyView

        await self.add_cog(OnboardingCog(self))
        await self.add_cog(GitHubCog(self))

        # Re-register the persistent verification button so it keeps working
        # across restarts.
        self.add_view(VerifyView(self))

        # Guild-scoped command sync: commands appear instantly instead of the
        # up-to-1-hour global propagation delay.
        guild = discord.Object(id=self.config.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    async def telemetry(self, message: str) -> None:
        """Post an operational event to the telemetry channel. Best effort."""
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
