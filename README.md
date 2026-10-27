# Stock Alerts → Pushover

Sends a Pushover push notification when, for any ticker on your watchlist:

| Event | Source | Default poll |
|---|---|---|
| Company news | Finnhub `/company-news` | 5 min |
| Trading halt / resumption | Nasdaq Trader halts RSS (all US exchanges) | 30 s |
| Price move ≥ 5% vs. previous close | Finnhub `/quote` | 60 s |
| 10-Q filed | SEC EDGAR submissions API | 5 min |

## Setup
1. Pushover: install the app, copy your **User Key**, and create an Application at pushover.net/apps/build for the **API Token**.
2. Finnhub: get a free API key at finnhub.io (free tier = 60 calls/min).
3. `cp .env.example .env` and fill it in.
4. Log in to GitHub's registry once (the image is private): `docker login ghcr.io -u JaxBuckeye` with a token that has `read:packages`.
5. `docker compose pull && docker compose up -d`
6. `docker compose logs -f`

To update after pushing new code: wait for the GitHub Action to finish, then run step 5 again.

Test first with `DRY_RUN=true` to see alerts in the logs without sending anything.

Pushover is optional: leave `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` both unset and alerts are written to the logs instead. Setting only one of them stops the app with an error.

## Behavior notes
- First run per ticker/source "seeds" existing items silently, so you don't get a flood of old news/filings.
- Move alerts fire once per direction per day, then again each time the move crosses the next multiple of the threshold (5%, 10%, 15%...).
- Halts are sent at Pushover priority 1 (bypasses quiet hours); change `priority` in `app/main.py` to 2 for emergency/repeat-until-acknowledged.
- State is in the `/data` volume (SQLite), so restarts don't duplicate alerts.
- Rate budget: price checks use 1 Finnhub call per ticker per cycle, news another. ~25 tickers fits comfortably in the free tier at default intervals; raise the intervals for larger lists.
- Pushover free apps allow 10,000 messages/month.
