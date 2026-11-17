# Operations guide — Sottocosto Oggi

## Before enabling production

1. Revoke the Telegram token exposed in the public `sottocosto-oggi` repository using @BotFather. Generate a new token.
2. Update the `TELEGRAM_BOT_TOKEN` GitHub Actions secret in this repository. Never paste the token into issues, logs, frontend code or pull requests.
3. Verify `TELEGRAM_CHANNEL_ID`, `AMAZON_CREDENTIAL_ID`, `AMAZON_CREDENTIAL_SECRET`, `AMAZON_PARTNER_TAG` secrets.
4. Check CI results on the pull request and perform a manual smoke test before merging.
5. Configure GitHub Environment `telegram-publishing` and its approval rules for the manual publication workflow.

## Emergency pause

Set repository **Settings → Secrets and variables → Actions → Variables → New repository variable**:

- Name: `BOT_PAUSED`
- Value: `true`

The scheduled bot job will be skipped. Set it to `false` or remove the variable to resume. Already running jobs are not interrupted; cancel them from Actions if necessary. The separate manual publishing workflow is unaffected.

## Monitoring

- Check Actions → Sottocosto Oggi Bot for execution failures and unusual runtime.
- Inspect Telegram posts for invalid prices, duplicates and broken links.
- Cache-based `posted_deals.json` and `daily_stats.json` are **not a durable database**. Cache eviction, restoration failures, or simultaneous external triggers can lose history. Do not rely on this storage for financial-grade price history.
- The current dashboard's AI-assisted product discovery is **not a verified source of live Amazon prices**.
- The legacy Prime Day 2026 campaign dates are fixed in the code and must be updated before any future campaign.

## Next architecture milestone

Replace the cache-based state with a durable datastore and atomic deduplication, then separate offer collection, scoring, approval policy and publishing into independent jobs. Use authenticated server-side endpoints and official permitted product data sources. Add telemetry and failure alerts before increasing posting frequency.
