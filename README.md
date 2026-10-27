# Stock Alerts → Pushover / Discord / SMS

Alerts for every ticker on a shared watchlist that people manage from Discord.

| Event | Source | Default poll |
|---|---|---|
| Company news | Finnhub | 5 min |
| Trading halt / resumption | Nasdaq Trader halts RSS | 30 s |
| Price move ≥ 5% vs. previous close | Finnhub | 60 s |
| 10-Q / 8-K filings (+amendments), with 8-K item descriptions | SEC EDGAR | 5 min |
| Earnings reminders (day before and day of) | Finnhub earnings calendar | 30 min |
| Investor calls / events (detected in headlines and press releases) | news + company sites | with news/sites |
| New press releases on the company's own website | auto-discovered newsroom or RSS | 15 min |

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

1. `cp .env.example .env` and fill it in.
2. `docker compose pull && docker compose up -d`
3. `docker compose logs -f`

To update after pushing new code: wait for the GitHub Action to finish, then run step 2 again.
State lives in the `/data` volume; the container user must be able to write to it.

## Notes
- First check per ticker/source records existing items silently; only new ones alert.
- Website monitoring reads the company's homepage (from Finnhub), finds a newsroom page and RSS feed, honors robots.txt, and checks every 15 minutes. JavaScript-rendered or bot-blocking sites may not work; set a URL with `/watch site`.
- Investor-call detection is keyword-based (conference call, webcast, "to host", "to report results", etc.). Earnings reminders give the date and before/after-market timing; dial-in details come from the company's announcement when they publish it.
- The same headline from news and a company site is only alerted once.
- SMS requires Twilio; US carriers require A2P 10DLC or toll-free verification, and trial accounts only text verified numbers.
