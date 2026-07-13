"""Member onboarding.

- Assigns the unverified role when someone joins.
- Greets new members per WELCOME_MODE. The default "roster" mode keeps
  exactly one welcome message in the welcome channel, mentioning everyone
  who hasn't verified yet: reposted on each join (pinging only the
  newcomer), silently edited as members verify or leave, and deleted once
  nobody is pending.
- Posts the server rules (from the rules markdown file) and hosts the
  persistent "Initialize" button that swaps the unverified role for the
  member role once someone agrees to them.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
    from ..client import Sodutod

log = logging.getLogger(__name__)

VERIFY_BUTTON_ID = "sodutod:verify"

# Embed descriptions cap at 4096 chars; stay under it with headroom.
EMBED_CHUNK_SIZE = 4000


def _chunk_markdown(text: str, size: int = EMBED_CHUNK_SIZE) -> list[str]:
    """Split markdown into embed-sized chunks along paragraph boundaries."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > size and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class VerifyView(discord.ui.View):
    """Persistent view attached to the verification message."""

    def __init__(self, bot: "Sodutod") -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Initialize",
        style=discord.ButtonStyle.success,
        custom_id=VERIFY_BUTTON_ID,
        emoji="\N{HIGH VOLTAGE SIGN}",
    )
    async def verify(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        config = self.bot.config
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "This only works inside the server.", ephemeral=True
            )
            return

        member_role = guild.get_role(config.role_member_id)
        unverified = guild.get_role(config.role_unverified_id)
        if member_role is None:
            log.error("Member role %s not found", config.role_member_id)
            await interaction.response.send_message(
                "Something is misconfigured on my end — the staff has been notified.",
                ephemeral=True,
            )
            await self.bot.telemetry(
                f"⚠️ Verification failed: member role `{config.role_member_id}` not found."
            )
            return

        if member_role in member.roles:
            await interaction.response.send_message(
                "You're already on the network.", ephemeral=True
            )
            return

        try:
            await member.add_roles(member_role, reason="rules verification")
            if unverified is not None and unverified in member.roles:
                await member.remove_roles(unverified, reason="rules verification")
        except discord.Forbidden:
            log.warning("Missing permissions to update roles for %s", member)
            await interaction.response.send_message(
                "I couldn't update your roles — the staff needs to check my "
                "role position and permissions.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"✅ **Boot sequence complete.** You're now a **{member_role.name}** "
            f"on the network — welcome to {guild.name}.",
            ephemeral=True,
        )
        old_name = unverified.name if unverified else "unverified"
        await self.bot.telemetry(
            f"🔓 {member.mention} verified: {old_name} → {member_role.name}"
        )

        cog = self.bot.get_cog("Onboarding")
        if isinstance(cog, OnboardingCog):
            await cog.member_verified(member)


class OnboardingCog(commands.Cog, name="Onboarding"):
    def __init__(self, bot: "Sodutod") -> None:
        self.bot = bot
        self.config = bot.config
        self.state_path = Path(self.config.state_dir) / "onboarding_state.json"
        self._roster_reconciled = False

    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state))

    async def _onboard(self, member: discord.Member) -> None:
        guild = member.guild
        unverified = guild.get_role(self.config.role_unverified_id)
        if unverified is not None and unverified not in member.roles:
            try:
                await member.add_roles(unverified, reason="new arrival")
                await self.bot.telemetry(
                    f"📥 {member.mention} joined — assigned **{unverified.name}**",
                    verbose=True,
                )
            except discord.Forbidden:
                log.warning("Missing permissions to assign join role to %s", member)
                await self.bot.telemetry(
                    f"⚠️ Couldn't assign **{unverified.name}** to {member.mention} — "
                    "check my role position and permissions."
                )

        mode = self.config.welcome_mode
        if mode == "off":
            return

        if mode == "roster":
            state = self._load_state()
            pending = state.setdefault("pending_ids", [])
            if member.id not in pending:
                pending.append(member.id)
            self._save_state(state)
            await self._refresh_roster(guild, ping=member)
            return

        rules_channel = guild.get_channel(self.config.channel_rules_id)
        rules_ref = rules_channel.mention if rules_channel else "the rules channel"

        if mode == "dm":
            embed = discord.Embed(
                title=f"📡 Welcome to {guild.name}",
                description=(
                    f"Hey {member.display_name} — your identity packet reached "
                    "the network.\n\n"
                    f"Head to {rules_ref}, read the short rundown, and press "
                    "**Initialize** to unlock the rest of the server."
                ),
                color=discord.Color.blurple(),
            )
            try:
                await member.send(embed=embed)
                await self.bot.telemetry(
                    f"✉️ Sent welcome DM to {member.mention}", verbose=True
                )
            except discord.Forbidden:
                # Member has server DMs disabled; they'll find the rules
                # channel on their own since it's one of the few channels
                # visible before verification.
                log.info("Cannot DM %s; skipping welcome", member)
                await self.bot.telemetry(
                    f"✉️ Couldn't DM {member.mention} (server DMs disabled) — "
                    "skipped the welcome",
                    verbose=True,
                )
            return

        # mode == "public"
        channel = guild.get_channel(self.config.channel_welcome_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="📡 Identity packet received",
            description=(
                f"{member.mention} appeared on the network.\n"
                f"Read {rules_ref} and press **Initialize** to complete "
                "the handshake."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await channel.send(embed=embed)
            await self.bot.telemetry(
                f"📣 Posted welcome embed for {member.mention} in {channel.mention}",
                verbose=True,
            )
        except discord.Forbidden:
            log.warning("Cannot send welcome message in the welcome channel")
            await self.bot.telemetry(
                f"⚠️ Couldn't post the welcome embed in {channel.mention} — "
                "check my channel overrides."
            )

    async def _refresh_roster(
        self, guild: discord.Guild, ping: discord.Member | None = None
    ) -> None:
        """Bring the single roster welcome message in line with reality.

        Called with ``ping`` on a new join (delete + repost at the bottom,
        notifying only the newcomer — Discord edits never ping, so an edit
        would leave later joiners unnotified), and without it when someone
        verifies or leaves (silent in-place edit, or deletion once nobody
        is pending).
        """
        channel = guild.get_channel(self.config.channel_welcome_id)
        if not isinstance(channel, discord.TextChannel):
            return

        state = self._load_state()
        member_role = guild.get_role(self.config.role_member_id)
        pending: list[int] = []
        for member_id in state.get("pending_ids", []):
            candidate = guild.get_member(member_id)
            if candidate is None or candidate.bot:
                continue
            if member_role is not None and member_role in candidate.roles:
                continue
            pending.append(member_id)
        state["pending_ids"] = pending

        old_message = None
        old_id = state.get("welcome_message_id")
        if old_id:
            try:
                old_message = await channel.fetch_message(old_id)
            except discord.NotFound:
                pass
            except discord.DiscordException:
                log.warning("Couldn't fetch welcome message %s", old_id)

        if not pending:
            if old_message is not None:
                try:
                    await old_message.delete()
                    await self.bot.telemetry(
                        "📋 Deleted the welcome roster — nobody pending",
                        verbose=True,
                    )
                except discord.DiscordException:
                    log.warning("Couldn't delete welcome message %s", old_id)
            state["welcome_message_id"] = None
            self._save_state(state)
            return

        rules_channel = guild.get_channel(self.config.channel_rules_id)
        rules_ref = rules_channel.mention if rules_channel else "the rules channel"
        mentions = " ".join(f"<@{member_id}>" for member_id in pending)
        packets = "packet" if len(pending) == 1 else "packets"
        embed = discord.Embed(
            title=f"📡 Identity {packets} received",
            description=(
                f"Welcome to {guild.name}! Read {rules_ref} and press "
                "**Initialize** to unlock the rest of the server."
            ),
            color=discord.Color.blurple(),
        )

        try:
            if ping is not None:
                if old_message is not None:
                    await old_message.delete()
                message = await channel.send(
                    content=mentions,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(
                        users=[ping], everyone=False, roles=False
                    ),
                )
                state["welcome_message_id"] = message.id
                await self.bot.telemetry(
                    f"📋 Reposted the welcome roster for {ping.mention} — "
                    f"{len(pending)} pending",
                    verbose=True,
                )
            elif old_message is not None:
                await old_message.edit(content=mentions, embed=embed)
                await self.bot.telemetry(
                    f"📋 Edited the welcome roster — {len(pending)} pending",
                    verbose=True,
                )
            else:
                message = await channel.send(
                    content=mentions,
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                state["welcome_message_id"] = message.id
                await self.bot.telemetry(
                    f"📋 Recreated the welcome roster — {len(pending)} pending",
                    verbose=True,
                )
        except discord.Forbidden:
            log.warning("Cannot post in the welcome channel")
            await self.bot.telemetry(
                f"⚠️ Couldn't maintain the welcome roster in {channel.mention} — "
                "check my channel overrides."
            )
            return
        self._save_state(state)

    async def member_verified(self, member: discord.Member) -> None:
        """Drop a member from the welcome roster once they verify."""
        if self.config.welcome_mode != "roster":
            return
        state = self._load_state()
        if member.id not in state.get("pending_ids", []):
            return
        state["pending_ids"].remove(member.id)
        self._save_state(state)
        await self._refresh_roster(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if self.config.welcome_mode != "roster":
            return
        state = self._load_state()
        if member.id not in state.get("pending_ids", []):
            return
        state["pending_ids"].remove(member.id)
        self._save_state(state)
        await self.bot.telemetry(
            f"📤 **{member.display_name}** left before initializing — "
            "removed from the welcome roster",
            verbose=True,
        )
        await self._refresh_roster(member.guild)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Reconcile the roster after downtime: members may have verified or
        # left while the bot was offline.
        if self.config.welcome_mode != "roster" or self._roster_reconciled:
            return
        self._roster_reconciled = True
        guild = self.bot.get_guild(self.config.guild_id)
        if guild is not None and self._load_state().get("pending_ids"):
            await self._refresh_roster(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        # If Membership Screening is enabled, wait until the member completes
        # it (handled in on_member_update below).
        if member.pending:
            return
        await self._onboard(member)

    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        if before.pending and not after.pending and not after.bot:
            await self._onboard(after)

    @app_commands.command(
        name="post-rules",
        description="Post (or refresh) the rules and the Initialize button in the rules channel.",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def post_rules(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        channel = guild.get_channel(self.config.channel_rules_id) if guild else None
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Rules channel not found — check `CHANNEL_RULES_ID`.",
                ephemeral=True,
            )
            return

        try:
            rules_text = Path(self.config.rules_path).read_text().strip()
        except OSError:
            await interaction.response.send_message(
                f"Couldn't read the rules file at `{self.config.rules_path}`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Repost from scratch so rerunning after a rules edit never leaves
        # stale copies behind. Only the bot's own messages are touched.
        assert self.bot.user is not None
        async for message in channel.history(limit=100):
            if message.author.id == self.bot.user.id:
                await message.delete()

        for chunk in _chunk_markdown(rules_text):
            await channel.send(
                embed=discord.Embed(description=chunk, color=discord.Color.blurple())
            )

        member_role = guild.get_role(self.config.role_member_id)
        unverified = guild.get_role(self.config.role_unverified_id)
        member_name = member_role.name if member_role else "member"
        unverified_name = unverified.name if unverified else "unverified"
        verify_embed = discord.Embed(
            title="⚡ Unlock the network",
            description=(
                "Pressing **Initialize** means you agree to the above. Your "
                f"**{unverified_name}** role is swapped for **{member_name}**, "
                "and the rest of the server unlocks."
            ),
            color=discord.Color.green(),
        )
        await channel.send(embed=verify_embed, view=VerifyView(self.bot))
        await interaction.followup.send(
            f"Rules and Initialize button posted in {channel.mention}.",
            ephemeral=True,
        )
        await self.bot.telemetry(
            f"📜 {interaction.user.mention} refreshed the rules post in "
            f"{channel.mention}"
        )
