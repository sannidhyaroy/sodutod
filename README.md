<div align="center">
  <img src="assets/sodutod.png" alt="sodutod Logo" width="180"/>
  <h1 style="font-weight: 700; font-size: 4em; margin: 0; padding-top: 0;">sodutod</h1>
  <p>
  a soduto daemon · pid 1 of soduto labs
  </p>
  <div style="margin-bottom: 1em">
  <a href="https://github.com/sannidhyaroy/sodutod/blob/main/LICENSE"><img src="https://img.shields.io/github/license/sannidhyaroy/sodutod.svg?color=B0BB88&style=flat-square" alt="AGPL Licensed"></a>
  <a href="https://github.com/sannidhyaroy/sodutod/issues"><img alt="GitHub issues" src="https://img.shields.io/github/issues/sannidhyaroy/sodutod?color=B0BB88&style=flat-square"></a>
  <a href="https://github.com/sannidhyaroy/sodutod/commits/main"><img src="https://img.shields.io/github/last-commit/sannidhyaroy/sodutod/main?color=B0BB88&style=flat-square" alt="Last Commit"></a>
  <a href="https://github.com/sannidhyaroy/sodutod/actions/workflows/docker.yml"><img alt="Docker Build" src="https://img.shields.io/github/actions/workflow/status/sannidhyaroy/sodutod/docker.yml?branch=main&color=B0BB88&style=flat-square&label=docker"></a>
  </div>
  <p>
  sodutod is the house bot of <b>Soduto Labs</b>, the community server for <a href="https://github.com/sannidhyaroy/Soduto">Soduto</a> — a KDE Connect compatible application for macOS. It onboards new members, runs the verification gate that unlocks the server, and relays GitHub activity into Discord.
  </p>
</div>

---
## **Navigation**
- [Features](#features)
  - [Onboarding](#onboarding)
  - [Verification](#verification)
  - [GitHub Relay](#github-relay)
  - [Telemetry](#telemetry)
  - [Housekeeping](#housekeeping)
- [Setup](#setup)
  - [Create the Discord Application](#create-the-discord-application)
  - [Server Configuration](#server-configuration)
  - [Bot Configuration](#bot-configuration)
- [Running Locally](#running-locally)
- [Deployment](#deployment)
- [Debugging](#debugging)
- [Get in touch](#get-in-touch)
- [FAQ](#faq)
  - [Why "sodutod"?](#why-sodutod)
  - [Is this an official Soduto component?](#is-this-an-official-soduto-component)
  - [Can I run it for my own server?](#can-i-run-it-for-my-own-server)
  - [Why does verification need a bot at all?](#why-does-verification-need-a-bot-at-all)
- [License](#license)
---
## Features

### Onboarding
- [x] Assign the unverified role to new arrivals automatically
- [x] Welcome roster: a single self-maintaining welcome message mentioning everyone not yet verified — reposted on join (pinging only the newcomer), silently edited as members verify or leave, deleted once nobody is pending
- [x] Alternate welcome modes: personal DM, one embed per join, or off (`WELCOME_MODE`)
- [x] Roster reconciliation after downtime (members who verified or left while the bot was offline are pruned on startup)

### Verification
- [x] `/post-rules` posts the server rules (from [`rules.md`](rules.md)) plus a persistent **Initialize** button into the rules channel — rerun it after editing the rules and the old post is replaced cleanly
- [x] Pressing **Initialize** swaps the unverified role for the member role and unlocks the server
- [x] Button survives bot restarts

### GitHub Relay
- [x] Announce new releases (and pre-releases) in the releases channel
- [x] Sync release edits: if release notes are edited on GitHub, the original announcement embed is updated in place
- [x] `/release` — show the latest release
- [x] `/issue <number>` — look up an issue or PR
- [ ] `/report` — file structured GitHub issues from bug-report forum posts

### Telemetry
- [x] Operational events (verifications, announcements, misconfigurations) posted to the telemetry channel

### Housekeeping
- [ ] Promotion commands with an audit trail
- [ ] Invite-based role grants (e.g. a tester invite that lands with the tester role)
- [ ] Automod escalation summaries

---
## Setup

### Create the Discord Application

- Go to the [Discord Developer Portal](https://discord.com/developers/applications) and create a **New Application** named `sodutod`.
- Under **Bot**:
  - Copy the token (this is `DISCORD_TOKEN`).
  - Enable **Server Members Intent** (required for join events and role management). Message Content intent is *not* needed.
- Invite the bot with this URL (replace `CLIENT_ID` with the app's Application ID):
  ```
  https://discord.com/api/oauth2/authorize?client_id=CLIENT_ID&scope=bot%20applications.commands&permissions=268520448
  ```
  That permission set is: Manage Roles, View Channels, Send Messages, Embed Links, Read Message History.

> [!NOTE]
> Name the application before inviting it — the managed role Discord creates takes the bot's name and can't be renamed afterwards.

### Server Configuration

- **Role hierarchy**: drag the bot's managed role *above* the roles it manages (it can only manage roles below its own), but below your staff roles.
- **Channel overrides**: give the bot's role an explicit *View Channel + Send Messages* override on the rules channel, the releases channel, and the telemetry channel — these are typically read-only or staff-locked.

> [!IMPORTANT]
> If the verification gate relies on `@everyone` being denied *View Channels* server-wide, verify it with `Server Settings → Roles → View Server As Role` for both `@everyone` and the unverified role. Permission leaks here are the most common misconfiguration.

### Bot Configuration

Configuration is environment-based — copy the template and fill in the IDs:

```bash
cp .env.example .env
```

| Variable               | Required | Description                                                                                                   |
| ---------------------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| `DISCORD_TOKEN`        | Yes      | Bot token from the Developer Portal                                                                           |
| `GUILD_ID`             | Yes      | The server's ID                                                                                               |
| `ROLE_UNVERIFIED_ID`   | Yes      | Role assigned on join, before verification                                                                    |
| `ROLE_MEMBER_ID`       | Yes      | Role granted when the member agrees to the rules                                                              |
| `CHANNEL_RULES_ID`     | Yes      | Channel hosting the rules and the Initialize button                                                           |
| `CHANNEL_WELCOME_ID`   | Yes      | Channel for welcome messages                                                                                  |
| `CHANNEL_RELEASES_ID`  | Yes      | Channel for release announcements                                                                             |
| `CHANNEL_TELEMETRY_ID` | Yes      | Channel for the bot's operational telemetry                                                                   |
| `GITHUB_REPO`          | No       | Repo to watch (default: `sannidhyaroy/Soduto`)                                                                |
| `GITHUB_TOKEN`         | No       | Raises the API rate limit from 60/h to 5000/h — a fine-grained PAT with read-only Contents + Issues is enough |
| `RELEASE_POLL_SECONDS` | No       | Release poll interval (default: `300`)                                                                        |
| `STATE_DIR`            | No       | Where the bot keeps its small state files (default: `./data`)                                                 |
| `RULES_PATH`           | No       | Markdown file posted by `/post-rules` (default: `./rules.md`)                                                 |
| `WELCOME_MODE`         | No       | `roster` (default), `dm`, `public`, or `off`                                                                  |

<details><summary>Where do I find these IDs? 👀</summary>

Enable Developer Mode in Discord (`Settings → Advanced → Developer Mode`), then:
- **Server ID**: right-click the server icon → `Copy Server ID`
- **Role IDs**: `Server Settings → Roles` → right-click a role → `Copy Role ID`
- **Channel IDs**: right-click a channel → `Copy Channel ID`

</details>

---
## Running Locally

sodutod is a Python 3.14 project managed with [uv](https://docs.astral.sh/uv/) — dependencies resolve automatically on first run:

```bash
uv run main.py
```

Once the bot is online, run `/post-rules` in the server (requires *Manage Server*) to post the rules and the **Initialize** button. This only needs to be done once — the button persists. Rerun it any time [`rules.md`](rules.md) changes.

---
## Deployment

Docker images are built by GitHub Actions on every push to `main` (and on `v*` tags) and published to `ghcr.io/sannidhyaroy/sodutod` for amd64 and arm64. On the server:

```bash
docker compose up -d     # pulls ghcr.io/sannidhyaroy/sodutod:latest
docker compose logs -f   # watch it come up
```

To update to the latest image:

```bash
docker compose pull && docker compose up -d
```

State (the welcome roster and announced releases) lives in the `bot-data` volume, so restarts and redeploys won't re-announce old releases or drop pending members.

> [!NOTE]
> The ghcr package is private by default after the first push — either make it public in the package's GitHub settings, or `docker login ghcr.io` on the server with a PAT that has `read:packages`.

<details><summary>Building the image locally instead? 👀</summary>

Swap `image:` for `build: .` in [`docker-compose.yml`](docker-compose.yml) and run:

```bash
docker compose up -d --build
```

</details>

---
## Debugging

sodutod logs to stdout, so `docker compose logs -f` (deployed) or the terminal (local) shows everything. Operational events are additionally mirrored to the telemetry channel on Discord, so day-to-day health is visible without shell access:

- 🔓 member verifications
- 📦 release announcements and ✏️ edit-syncs
- ⚠️ misconfigurations the bot notices about itself

---
## Get in touch

To ask a question, offer suggestions or share an idea, please use the [discussions tab](https://github.com/sannidhyaroy/sodutod/discussions) of this repository.

If you spot any bugs or vulnerabilities, please [create an issue](https://github.com/sannidhyaroy/sodutod/issues/). It's always a good idea to make sure there aren't any similar issues open, before creating a new one!

---
## FAQ

### Why "sodutod"?

It follows the macOS daemon naming convention (`launchd`, `watchdogd`) because that's what it is: the Soduto daemon, the background process that keeps Soduto Labs running. Fitting for the community of a macOS app.

### Is this an official Soduto component?

It's the house bot of Soduto Labs, the community server for the [actively maintained Soduto fork](https://github.com/sannidhyaroy/Soduto). It's not part of the Soduto app itself and doesn't speak the KDE Connect protocol — it speaks Discord.

### Can I run it for my own server?

Yes. Nothing is hardcoded — all roles and channels are configured by ID (see [Bot Configuration](#bot-configuration)), the rules content is a markdown file, and the GitHub repo it watches is configurable. Point the `.env` at your own server and repo and it'll serve you just as faithfully. It's AGPL, so keep it open.

### Why does verification need a bot at all?

Discord can't do it natively: there's no built-in "assign a role on join," and Membership Screening only flips members from pending to member — it never assigns or swaps roles. Gating a server behind an agree-to-rules role swap requires a bot.

---
## License

sodutod is licensed under the [GNU Affero General Public License v3.0](https://github.com/sannidhyaroy/sodutod/blob/main/LICENSE).
