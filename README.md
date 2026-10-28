# Stock Alerts → Pushover / Discord / SMS

Alerts for every ticker on a shared watchlist that people manage from Discord.

| Event | Source | Default poll |
|---|---|---|
| Company news | Finnhub | 5 min |
| Trading halt / resumption | Nasdaq Trader halts RSS | 30 s |
| Price move ≥ 5% vs. previous close | Finnhub | 60 s |
| 10-Q / 8-K filings (+amendments), with 8-K item descriptions | SEC EDGAR | 5 min |
| Form 4 insider trades (who, role, buy/sell, shares, price, holdings after) | SEC EDGAR | 5 min |
| Schedule 13D stakes (filer, % owned, stated purpose); 13G optional | SEC EDGAR | 5 min |
| Earnings reminders (day before and day of) | Finnhub earnings calendar | 30 min |
| Investor calls / events (detected in headlines and press releases) | news + company sites | with news/sites |
| New press releases on the company's own website | auto-discovered newsroom or RSS | 15 min |
| CVRs: news and filings about the assets a CVR pays on, and CVR payment announcements | SEC EDGAR + Google News | 30 min |

## Web page
Open `http://<server>:8080`. On the very first visit you create the login: the page asks for a one-time **setup code**,
printed in the container logs (`First-time setup: ... enter setup code XXXXXXXX`), then you pick a username and password.
The layout follows Sonarr/Radarr: a sidebar with sub-menus, a toolbar per page, dark theme.

- **Activity** (front page) is a live feed of every alert sent (kept 90 days), with counts, channel status, filters by
  alert type and ticker. New alerts appear every 30 seconds without reloading.
- **Watchlist** shows each ticker's newsroom and feed, and whether its site blocks automated access.
- **CVRs** lists tracked CVRs with what was found, and lets you add one or edit its search terms.
- **Settings** has a section per area (Required, Discord, SEC filings, CVRs, Jobs, ...). A value saved here wins over
  `.env`; each shows whether it's *set here*, *from .env* or the *default*. **Copy from .env** moves everything at once,
  after which `.env` can be emptied. Saving restarts the app (a few seconds). Secrets are never shown.
- **System**: *Status* (version, uptime, channels, checks, blocked sites), *Logs* (recent log lines, filter to warnings
  or errors) and *Updates* (the installed build vs. the latest commits on GitHub; update by clicking Update in Dockge).
- Passwords are stored hashed; 5 wrong passwords lock logins from that address for 5 minutes. Keep port 8080 on your
  LAN (don't forward it to the internet) since the page is plain HTTP.
- Forgot the password? `docker exec stock-alerts python -m app.reset_login` prints a new setup code (settings are kept).

## CVRs
`/cvr add CYCN` (or **Add CVR** on the web page) takes the ticker of the company that *issued* the CVR, even if it's
delisted or renamed. The lookup:
1. finds the company at the SEC by its current or former ticker (CYCN is now Korsana Biosciences, KRSA),
2. finds the CVR agreement with SEC full-text search, and from it who owes the payments, the payment/milestone
   definitions, and the companies the assets were sold or licensed to (for CYCN: Akebia and Tisento),
3. reads the merger prospectus for drug/program names, keeping only those discussed next to the CVR or its
   counterparties (for CYCN: praliciguat, zagociguat, CY3018, olinciguat), not the acquirer's own pipeline.

Then every 30 minutes it alerts (kind `cvr`, posted to a `#cycn` channel if you have one) on:
- the obligor's SEC filings **only** when they mention an asset, a counterparty or a CVR payment; its other 8-Ks are ignored,
- any company's SEC filings that mention an asset (licensees, buyers, a spin-out's IPO). Companies outside the deal need
  at least two mentions, so a passing mention in an executive's bio doesn't alert,
- Google News stories that mention an asset, or the issuer together with "CVR".

**Assets** are searched on their own. **Companies** are only searched together with the issuer's name
(`"Akebia" "Cyclerion"`), since a company name alone would match all of that company's news. Edit either list with
`/cvr asset` or on the web page. The first check of any new term records what already exists, quietly.

Discord: `/cvr add`, `/cvr remove`, `/cvr list`, `/cvr info TICKER`, `/cvr asset TICKER add|remove NAME [asset|company]`.
Preview a lookup without saving it: `docker exec stock-alerts python -m app.cvr CYCN`.

## Discord commands
- `/watch add AAPL, TSLA NVDA` – validates tickers, adds them, replies with the full list
- `/watch remove TSLA` – removes, replies with the full list
- `/watch list` – shows the list (🌐 = company newsroom monitored)
- `/watch sites` – shows the news page / RSS feed monitored for every ticker
- `/watch site AAPL` – shows the one monitored for AAPL
- `/watch site AAPL https://www.apple.com/newsroom/` – override the monitored newsroom/RSS URL (`auto` re-detects)

### Discord bot setup
1. discord.com/developers/applications → **New Application** → **Bot** → **Reset Token** → copy into `DISCORD_BOT_TOKEN`.
2. **OAuth2 → URL Generator**: scopes `bot` and `applications.commands`, no extra permissions needed. Open the URL and invite it to your server.
3. Discord **Settings → Advanced → Developer Mode**, then right-click your server → **Copy Server ID** into `DISCORD_GUILD_ID`.
4. Optional: `DISCORD_ALLOWED_ROLE_ID` / `DISCORD_COMMAND_CHANNEL_ID` to restrict who and where.
5. The alert *webhook* (`DISCORD_WEBHOOK_URL`) is separate from the bot. Use both.

## Per-ticker channels
Create a text channel named after a ticker (e.g. `#bolt` for BOLT) and the bot posts that ticker's news, price moves,
filings, earnings reminders, halts, investor calls and website releases there. Give the bot **View Channel**, **Send
Messages** and **Embed Links** in that channel. `/watch list` shows `→ #channel` for tickers that have one.
By default alerts also still go to your general channel; set `DISCORD_TICKER_ONLY=true` to stop that for tickers with a channel.

## Deploy
GitHub Actions builds the image on every push to `main` and publishes it to `ghcr.io/jaxbuckeye/stock-alerts:latest`.

1. `docker compose pull && docker compose up -d` (publish port 8080 for the web page)
2. `docker compose logs -f`, copy the setup code, open `http://<server>:8080` and create your login.
3. Fill in the settings on the web page (or in `.env`, see `.env.example`).

To update after pushing new code: wait for the GitHub Action to finish, then run step 1 again.
If required settings are missing the app doesn't exit: the web page runs and alerts are paused until they're filled in.
State lives in the `/data` volume; the container user must be able to write to it.

## Notes
- First check per ticker/source records existing items silently; only new ones alert.
- Website monitoring (every 15 minutes, honoring robots.txt) reads three sources per ticker and alerts once per headline:
  the newsroom's RSS feed, the newsroom page, and news links on the company homepage. Many investor sites (Q4,
  Equisolve and similar) build their newsroom with JavaScript but serve a feed they don't link to, so standard feed
  addresses like `/rss/pressrelease.aspx` are tried too. Sites that refuse automated access (HTTP 403, e.g.
  Akamai-protected `ir.` sites) are logged once and skipped for 6 hours. `PRESS_WIRE_NEWS` (on by default) also
  searches GlobeNewswire, Business Wire, PR Newswire, ACCESS Newswire and Newsfile for each company's releases, which
  covers those blocked sites; law-firm "shareholder investigation" releases are ignored. Override a ticker's newsroom
  with `/watch site`.
- Investor-call detection is keyword-based (conference call, webcast, "to host", "to report results", etc.). Earnings reminders give the date and before/after-market timing; dial-in details come from the company's announcement when they publish it.
- The same headline from news and a company site is only alerted once.
- Form 4 / 13D / 13G use their own settings (`TRACK_FORM4`, `FORM4_CODES`, `TRACK_13D`, `TRACK_13G`), not `SEC_FORMS`,
  and their own alert kinds (`insider`, `stake`), so they are not texted unless you add them to `SMS_EVENTS`.
  Filings where a watched company is the *filer* (it took a stake in someone else) are skipped.
  A brand-new 13D is sent at priority 1 (Pushover high priority, Discord mention); amendments and Form 4s are normal.
- Turning these on (or changing the form settings) records existing filings silently, so there's no flood of old ones.
- SMS requires Twilio; US carriers require A2P 10DLC or toll-free verification, and trial accounts only text verified numbers.
