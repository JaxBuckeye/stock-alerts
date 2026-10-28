"""Discord bot: /watch commands, plus posting each ticker's alerts to a channel named after it."""
import asyncio
import logging
import re
import threading
from datetime import datetime, timezone

import discord
from discord import app_commands

from . import config as c
from . import health
from . import jobs
from . import notify as notify_mod
from .store import state

log = logging.getLogger("bot")
_bot = None
_warned = set()


# ------------------------------------------------------------ helpers
def parse_symbols(text):
    out = []
    for tok in re.split(r"[,\s]+", text.upper()):
        sym = c.norm(tok) if tok.strip() else ""
        if sym and re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", sym) and sym not in out:
            out.append(sym)
    return out


def chunks(lines, limit=1900):
    out, cur = [], ""
    for ln in lines:
        if cur and len(cur) + len(ln) + 1 > limit:
            out.append(cur)
            cur = ""
        cur += ln + "\n"
    if cur:
        out.append(cur)
    return out


def find_channel(sym):
    """Text channel named after the ticker (BOLT -> #bolt; BRK.B -> #brk-b or #brkb)."""
    if not _bot or not _bot.is_ready():
        return None
    low = sym.lower()
    names = {low, low.replace(".", "-"), low.replace(".", "")}
    for guild in list(_bot.guilds):
        if c.DISCORD_GUILD_ID and str(guild.id) != c.DISCORD_GUILD_ID:
            continue
        for ch in guild.text_channels:
            if ch.name in names:
                return ch
    return None


def describe_site(sym):
    row = state.get_site(sym)
    if not row:
        return "No website known yet (it's looked up shortly after a ticker is added)."
    src = row["feed_url"] or row["news_url"]
    if not src:
        return (f"Nothing found to monitor yet. Homepage: <{row['homepage'] or 'unknown'}>. "
                f"Set one with `/watch site {sym} <url>`.")
    kind = "RSS feed" if row["feed_url"] else "newsroom page"
    how = "set manually" if row["manual"] else "auto-detected"
    return f"{kind}, {how}: <{src}>"


def watchlist_embed(title="Current watchlist"):
    rows = state.watch_rows()
    lines = []
    for sym, name in rows:
        site = state.get_site(sym)
        mark = " 🌐" if site and (site["feed_url"] or site["news_url"]) else ""
        ch = find_channel(sym)
        chan = f" → {ch.mention}" if ch else ""
        lines.append(f"`{sym}` {name if name and name != sym else ''}{mark}{chan}")
    e = discord.Embed(title=f"{title} ({len(rows)})", description=("\n".join(lines) or "_Empty._")[:4000], color=0x3498DB)
    e.set_footer(text="🌐 = newsroom monitored (see /watch sites)  •  → = ticker has its own alert channel")
    return e


# -------------------------------------- posting alerts to ticker channels
def post_ticker(sym, title, message, url, kind, priority):
    """Called from the scheduler thread. None = no channel; True/False = sent / failed."""
    ch = find_channel(sym)
    if ch is None:
        return None
    me = ch.guild.me
    if me:
        p = ch.permissions_for(me)
        if not (p.view_channel and p.send_messages and p.embed_links):
            if ch.id not in _warned:
                log.warning("Bot lacks View/Send/Embed permission in #%s; grant it to post %s alerts", ch.name, sym)
                _warned.add(ch.id)
            return False
    embed = discord.Embed(title=title[:256], description=message[:4000], color=notify_mod.COLORS.get(kind, 0x95A5A6),
                          url=url if url and url.startswith(("http://", "https://")) else None)
    embed.timestamp = datetime.now(timezone.utc)
    content = c.DISCORD_MENTION if (c.DISCORD_MENTION and priority >= 1) else None
    try:
        asyncio.run_coroutine_threadsafe(ch.send(content=content, embed=embed), _bot.loop).result(timeout=20)
        return True
    except Exception:
        log.exception("Failed to post to #%s", ch.name)
        return False


# ----------------------------------------------------------- commands
def do_add(syms, who):
    added, existed, invalid, failed, skipped = [], [], [], [], []
    current = set(state.tickers())
    for sym in syms:
        if sym in current:
            existed.append(sym)
        elif len(current) + len(added) >= c.MAX_TICKERS:
            skipped.append(sym)
        else:
            try:
                prof = jobs.lookup_profile(sym)
            except Exception:
                log.exception("lookup failed for %s", sym)
                failed.append(sym)
                continue
            if not prof:
                invalid.append(sym)
                continue
            state.add_ticker(sym, prof.get("name") or sym, who)
            if prof.get("weburl"):
                state.upsert_site(sym, homepage=prof["weburl"])
            added.append(sym)
    return added, existed, invalid, failed, skipped


def fmt(label, syms):
    return f"{label} " + ", ".join(f"`{s}`" for s in syms) if syms else None


group = app_commands.Group(name="watch", description="Manage the stock watchlist", guild_only=True)


async def allowed(interaction):
    if c.DISCORD_CHANNEL_ID and str(interaction.channel_id) != c.DISCORD_CHANNEL_ID:
        await interaction.response.send_message(f"Please use <#{c.DISCORD_CHANNEL_ID}> for watchlist changes.", ephemeral=True)
        return False
    if c.DISCORD_ROLE_ID and not any(str(r.id) == c.DISCORD_ROLE_ID for r in getattr(interaction.user, "roles", [])):
        await interaction.response.send_message("You don't have the required role to change the watchlist.", ephemeral=True)
        return False
    return True


@group.command(name="add", description="Add tickers to the watchlist")
@app_commands.describe(tickers="Ticker symbols, comma or space separated (e.g. AAPL, TSLA NVDA)")
async def add_cmd(interaction: discord.Interaction, tickers: str):
    if not await allowed(interaction):
        return
    syms = parse_symbols(tickers)[:20]
    if not syms:
        await interaction.response.send_message("I couldn't find any valid ticker symbols in that.", ephemeral=True)
        return
    await interaction.response.defer()
    added, existed, invalid, failed, skipped = await asyncio.to_thread(do_add, syms, str(interaction.user))
    lines = [x for x in (
        fmt(f"✅ Added by {interaction.user.display_name}:", added), fmt("ℹ️ Already watching:", existed),
        fmt("❌ Not found:", invalid), fmt("⚠️ Lookup failed, try again:", failed),
        fmt(f"⚠️ Limit of {c.MAX_TICKERS} reached, skipped:", skipped)) if x]
    await interaction.followup.send("\n".join(lines), embed=watchlist_embed())


@group.command(name="remove", description="Remove tickers from the watchlist")
@app_commands.describe(tickers="Ticker symbols, comma or space separated")
async def remove_cmd(interaction: discord.Interaction, tickers: str):
    if not await allowed(interaction):
        return
    syms = parse_symbols(tickers)[:50]
    removed = [s for s in syms if await asyncio.to_thread(state.remove_ticker, s)]
    missing = [s for s in syms if s not in removed]
    lines = [x for x in (fmt(f"🗑️ Removed by {interaction.user.display_name}:", removed),
                         fmt("ℹ️ Wasn't on the list:", missing)) if x] or ["No valid tickers given."]
    await interaction.response.send_message("\n".join(lines), embed=watchlist_embed())


@group.command(name="list", description="Show the current watchlist")
async def list_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=watchlist_embed())


@group.command(name="sites", description="Show which news page or RSS feed is monitored for each ticker")
async def sites_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    lines = [f"**{sym}**: {describe_site(sym)}" for sym, _ in state.watch_rows()]
    for part in chunks(lines) or ["The watchlist is empty."]:
        await interaction.followup.send(part)


@group.command(name="site", description="Show or set the news page/RSS URL monitored for a ticker ('auto' re-detects)")
@app_commands.describe(ticker="A ticker already on the watchlist",
                       url="Leave empty to view the current one. Newsroom page or RSS URL to set, or 'auto'")
async def site_cmd(interaction: discord.Interaction, ticker: str, url: str = None):
    sym = c.norm(ticker)
    if sym not in state.tickers():
        await interaction.response.send_message(f"`{sym}` isn't on the watchlist. Add it first.", ephemeral=True)
        return
    if url is None:
        await interaction.response.send_message(f"**{sym}**: {describe_site(sym)}")
        return
    if not await allowed(interaction):
        return
    if url.strip().lower() == "auto":
        state.upsert_site(sym, news_url=None, feed_url=None, manual=0, checked_ts=0)
        await interaction.response.send_message(f"🔄 `{sym}`: will re-detect the newsroom automatically.")
    elif url.startswith(("http://", "https://")):
        state.upsert_site(sym, news_url=url.strip(), feed_url=None, manual=1)
        await interaction.response.send_message(
            f"🌐 `{sym}`: now monitoring <{url.strip()}>. The first check records what's already there; only new items alert.")
    else:
        await interaction.response.send_message("URL must start with http:// or https:// (or use `auto`).", ephemeral=True)


# --------------------------------------------------------------- CVRs
cvr_group = app_commands.Group(name="cvr", description="Track contingent value rights (CVRs)", guild_only=True)


def cvr_embed(x):
    ob = x.get("obligor") or {}
    e = discord.Embed(title=f"{x['sym']} CVR · {x.get('name', '')}"[:256], color=notify_mod.COLORS["cvr"],
                      url=(x.get("agreement") or {}).get("url"))
    if x.get("summary"):
        e.description = x["summary"][:1500]
    e.add_field(name="Pays out from", value=(f"{ob.get('name') or 'unknown'}" +
                                            (f" ({ob['ticker']})" if ob.get("ticker") else ""))[:1024], inline=False)
    e.add_field(name="Assets (searched on their own)",
                value=", ".join(x.get("assets") or []) or "_none found_", inline=False)
    e.add_field(name="Companies (searched with the issuer's name)",
                value=", ".join(x.get("companies") or []) or "_none_", inline=False)
    if x.get("key_terms"):
        e.add_field(name="Key terms", value="\n".join(f"**{t['term']}**: {t['text'][:150]}" for t in x["key_terms"][:4])[:1024],
                    inline=False)
    for n in x.get("notes") or []:
        e.add_field(name="Note", value=n[:1024], inline=False)
    e.set_footer(text=f"Edit with /cvr asset or on the web page (port {c.WEB_PORT})")
    return e


def cvr_list_embed():
    rows = state.cvr_list()
    lines = [f"`{x['sym']}` {x.get('name', '')} → {', '.join((x.get('assets') or []) + (x.get('companies') or []))[:200]}"
             for x in rows]
    return discord.Embed(title=f"Tracked CVRs ({len(rows)})", description="\n".join(lines)[:4000] or "_None yet._",
                         color=notify_mod.COLORS["cvr"])


@cvr_group.command(name="add", description="Track the CVR issued by a company (it can be delisted or renamed)")
@app_commands.describe(ticker="Ticker of the company that issued the CVR, e.g. CYCN")
async def cvr_add_cmd(interaction: discord.Interaction, ticker: str):
    if not await allowed(interaction):
        return
    syms = parse_symbols(ticker)
    if not syms:
        await interaction.response.send_message("That doesn't look like a ticker.", ephemeral=True)
        return
    sym = syms[0]
    if state.cvr_get(sym):
        await interaction.response.send_message(f"`{sym}` is already tracked.", embed=cvr_embed(state.cvr_get(sym)))
        return
    await interaction.response.defer()
    from . import cvr
    try:
        info = await asyncio.to_thread(cvr.add, sym, str(interaction.user))
    except LookupError as e:
        await interaction.followup.send(f"❌ {e}")
        return
    except Exception as e:
        log.exception("CVR discovery failed for %s", sym)
        await interaction.followup.send(f"⚠️ Couldn't look up `{sym}` right now: {e}")
        return
    await interaction.followup.send(f"✅ Tracking the `{sym}` CVR (added by {interaction.user.display_name}). "
                                    "Existing filings and news are recorded quietly; only new ones alert.",
                                    embed=cvr_embed(info))


@cvr_group.command(name="remove", description="Stop tracking a CVR")
async def cvr_remove_cmd(interaction: discord.Interaction, ticker: str):
    if not await allowed(interaction):
        return
    sym = c.norm(ticker)
    ok = await asyncio.to_thread(state.cvr_remove, sym)
    await interaction.response.send_message(f"🗑️ Stopped tracking the `{sym}` CVR." if ok else f"`{sym}` wasn't tracked.",
                                            embed=cvr_list_embed())


@cvr_group.command(name="list", description="Show tracked CVRs")
async def cvr_list_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=cvr_list_embed())


@cvr_group.command(name="info", description="Show what a CVR pays on and what's being watched")
async def cvr_info_cmd(interaction: discord.Interaction, ticker: str):
    x = state.cvr_get(c.norm(ticker))
    if not x:
        await interaction.response.send_message(f"`{c.norm(ticker)}` isn't tracked. Use `/cvr add` first.", ephemeral=True)
        return
    await interaction.response.send_message(embed=cvr_embed(x))


@cvr_group.command(name="asset", description="Add or remove a search term for a CVR")
@app_commands.describe(ticker="CVR ticker", action="add or remove", name="Drug/program name, or a buyer/licensee company",
                       kind="asset = searched on its own; company = searched together with the issuer's name")
@app_commands.choices(action=[app_commands.Choice(name="add", value="add"), app_commands.Choice(name="remove", value="remove")],
                      kind=[app_commands.Choice(name="asset", value="assets"), app_commands.Choice(name="company", value="companies")])
async def cvr_asset_cmd(interaction: discord.Interaction, ticker: str, action: app_commands.Choice[str], name: str,
                        kind: app_commands.Choice[str] = None):
    if not await allowed(interaction):
        return
    sym = c.norm(ticker)
    x = state.cvr_get(sym)
    if not x:
        await interaction.response.send_message(f"`{sym}` isn't tracked. Use `/cvr add` first.", ephemeral=True)
        return
    field, name = (kind.value if kind else "assets"), name.strip()
    if action.value == "add":
        if name not in (x.get(field) or []):
            x[field] = (x.get(field) or []) + [name]
    else:
        for f in ("assets", "companies"):
            x[f] = [t for t in x.get(f) or [] if t.lower() != name.lower()]
    await asyncio.to_thread(state.cvr_put, sym, x)
    await interaction.response.send_message(f"Updated `{sym}`.", embed=cvr_embed(state.cvr_get(sym)))


# ------------------------------------------------------------- health
STATUS_COLORS = {"ok": 0x2ECC71, "warn": 0xF1C40F, "error": 0xE74C3C}
PRESENCE = {"ok": discord.Status.online, "warn": discord.Status.idle, "error": discord.Status.dnd}


def status_embed(r):
    title = {"ok": "🟢 Running normally", "warn": "🟡 Running, needs attention", "error": "🔴 Setup needed"}[r["status"]]
    e = discord.Embed(title=title, color=STATUS_COLORS[r["status"]])
    if r["problems"]:
        e.description = "\n".join(f"• {p}" for p in r["problems"][:8])[:2000]
    e.add_field(name="Up for", value=r["uptime"])
    e.add_field(name="Watching", value=f"{r['tickers']} tickers · {r['cvrs']} CVRs")
    e.add_field(name="Alerts (24h)", value=f"{r['alerts_24h']} · last {r['last_alert']}")
    lines = [f"{'✅' if not j['error'] else '⚠️'} **{j['name']}** every {j['every']}s · ran {j['last_run']}"
             if j["on"] else f"⏸️ **{j['name']}** off" for j in r["jobs"]]
    e.add_field(name="Checks", value="\n".join(lines)[:1024], inline=False)
    e.add_field(name="Channels", value=" · ".join(f"{'🟢' if on else '⚪'} {n}" for n, on in r["channels"]), inline=False)
    if r["blocked"]:
        e.add_field(name="Sites refusing access", value=", ".join(r["blocked"])[:1024], inline=False)
    e.set_footer(text=f"build {r['version']} · web page on port {c.WEB_PORT}")
    return e


@app_commands.command(name="status", description="Is Stock Alerts running? Health of every check")
@app_commands.guild_only()
async def status_cmd(interaction: discord.Interaction):
    r = await asyncio.to_thread(health.report)
    await interaction.response.send_message(embed=status_embed(r))


class WatchBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents(guilds=True))
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if c.DISCORD_GUILD_ID:
            guild = discord.Object(id=int(c.DISCORD_GUILD_ID))
            for cmd in (group, cvr_group, status_cmd):
                self.tree.add_command(cmd, guild=guild)
            await self.tree.sync(guild=guild)
        else:
            for cmd in (group, cvr_group, status_cmd):
                self.tree.add_command(cmd)
            await self.tree.sync()
        log.info("Slash commands synced")
        self.loop.create_task(self.presence_loop())

    async def presence_loop(self):
        """Live heartbeat: the bot's dot (green/yellow/red) and status line, refreshed every minute.
        If the app stops, Discord shows the bot offline."""
        await self.wait_until_ready()
        last = None
        while not self.is_closed():
            try:
                r = await asyncio.to_thread(health.report)
                now = (r["status"], health.status_line(r))
                if now != last:
                    await self.change_presence(status=PRESENCE[r["status"]], activity=discord.CustomActivity(name=now[1]))
                    last = now
            except Exception:
                log.exception("couldn't update the bot's status")
            await asyncio.sleep(60)

    async def on_ready(self):
        log.info("Discord bot connected as %s", self.user)


def start():
    global _bot
    _bot = WatchBot()
    if c.DISCORD_TICKER_CHANNELS:
        notify_mod.ticker_poster = post_ticker

    def runner():
        try:
            asyncio.run(_bot.start(c.DISCORD_BOT_TOKEN))
        except Exception:
            log.exception("Discord bot stopped")

    threading.Thread(target=runner, name="discord-bot", daemon=True).start()
