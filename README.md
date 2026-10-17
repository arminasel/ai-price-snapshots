# AI price snapshots

A dated record of AI model API list prices (USD per 1M tokens: input, output, cache read, cache write) for Anthropic, OpenAI, Google, OpenCode Zen and OpenCode Go.

- `prices/history.json`: one snapshot per day on which a price changed; the last snapshot is the current list.
- `prices/CHANGELOG.md`: what changed and when.
- Source: https://models.dev/api.json, the open model catalogue maintained by the OpenCode team, which links each provider's own pricing documentation.
- Updated once a day by `.github/workflows/prices.yml` running `scripts/update_prices.py` (standard-library Python) on GitHub's runner.

Read by AI Usage Tray to estimate API-equivalent costs. These are list prices, not invoices; check the provider's pricing page before budgeting.

## Capability index

`prices/index.json` holds the Artificial Analysis Intelligence Index per model (https://artificialanalysis.ai; attribution required for free use), keyed by the same model ids as the price list, for price/performance sorting. `scripts/update_index.py` refreshes it daily through the free Artificial Analysis data API when the repository secret `AA_API_KEY` is set; without it the file keeps its values (first values: a manual reading of the leaderboard on 2026-10-10).
