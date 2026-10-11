# Plaid Sandbox: setup and P1 handoff

## What is prepared

The finance page has an optional **Connect a test bank** section. It uses a separate local Node.js connector to launch Plaid Link, exchange its temporary public token privately, fetch synthetic checking/savings balances, synchronize recent transactions, and disconnect using `/item/remove`.

The user requested this preparation before P1's main integration is ready. This reprioritizes the earlier stretch-feature schedule; it does not make the core acceptance checks or backend integration complete. The user has since configured Sandbox credentials and supplied screenshots showing a successful connection with checking and savings balances. They reported that reviewing savings replaced the checking budget entry. The account review now matches entries by individual account ID and shows the total before and after confirmation. This correction has JavaScript syntax and whitespace checks only; no agent-run provider calls, browser walkthrough, or test suite were performed.

## Your setup steps

1. Create a developer account in the [Plaid Dashboard](https://dashboard.plaid.com/). Locate the client ID and **Sandbox** secret in its API Keys section. The [official Quickstart](https://plaid.com/docs/quickstart/) explains this setup.
2. Open the ignored `.env.plaid` file at the repository root and enter those values locally. If it does not exist, copy `.env.example` to `.env.plaid` first. Keep `PLAID_ENV=sandbox`. Do not paste credentials into chat or frontend JavaScript. The connector also accepts these values as process environment variables.
3. From the repository root, run:

   ```sh
   npm run plaid:sandbox
   ```

   Node.js 18+ is required. No new npm dependencies are needed for the connector. Its default address is `http://127.0.0.1:4100/#finance`; use the address printed by the process if you change `PLAID_DEMO_PORT`.

4. Open that address, choose **Finances → Connect a test bank**, and launch Link. Use only Plaid's synthetic Sandbox login. The Quickstart's standard credentials are `user_good` / `pass_good`; if requested, its test verification code is `1234`. Use a standard test institution for this first flow; institution-specific OAuth configuration remains later work.
5. Choose **Refresh bank data**. Transactions can take time to prepare, so refresh again shortly if history is initially empty. The page shows when balances and history were fetched.
6. Optionally choose **Review for budget** on each supported USD available balance. Each account creates its own entry using its opaque account ID; reviewing it again updates that same entry. Review the account name, balance, and before/after starting total, then confirm. Check for manually recorded duplicates before adding an account. The starting total labels sample cash separately. **Disconnect test bank** revokes the connected Sandbox Item; copied budget entries remain as auditable manual records.

The ordinary `file://` frontend remains usable for its local mock features. It displays connector setup instructions rather than attempting cross-origin token exchange. The connector serves only an explicit list of frontend assets; it does not expose repository files or environment files. No alternate automated preview of the previously blocked local file was attempted.

## Local connector boundary

`scripts/plaid-sandbox-server.cjs` binds only to `127.0.0.1` and calls only `https://sandbox.plaid.com`. Production configuration is rejected. It creates an opaque local HttpOnly/SameSite session, uses a CSRF token and exact-origin checks for mutations, and scopes each connected Item to that local session. This is an isolated development session, not P1's authenticated household authorization.

Client ID, secret, access token, raw provider IDs, transaction sync cursor, and original provider transaction records stay on the server. The frontend gets a short-lived Link token, the temporary public token returned by Link, and a reduced account/history projection. Plaid's SDK is loaded directly from its CDN only when the user starts a connection. No provider tokens are written to browser storage or added to agent conversations. See the official [Link Web SDK](https://plaid.com/docs/link/web/) and [token flow](https://plaid.com/docs/quickstart/).

Access tokens, connections, and sync state are **memory-only** in this development server. Restarting loses them and requires relinking. Before a planned restart, disconnect in the UI; if an old Sandbox Item remains after a restart, manage it in the Plaid Dashboard. P1 must supply durable protected token storage and household authorization before any deployed use.

| Route | Purpose |
| --- | --- |
| `GET /api/plaid/status` | Local session/setup status and reduced projection, including CSRF token |
| `POST /api/plaid/link-token` | Create a Sandbox Link token for Transactions with checking/savings filters |
| `POST /api/plaid/exchange` | Exchange a Sandbox public token; repeat requests for the same accepted public token reuse the local connection |
| `POST /api/plaid/refresh` | Fetch `/accounts/balance/get` and apply `/transactions/sync` pages |
| `POST /api/plaid/disconnect` | Revoke the Item and clear the local connection projection |

Requests are serialized per local session. Provider errors expose a bounded error code, rather than raw request/response objects containing tokens. The connector does not log request bodies, provider payloads, cookies, or secrets. Reads are on demand; there are no background polling promises, webhooks, payments, or production bank connections.

## Balance and history rules

- Use the `available` balance for selected USD depository accounts. Unknown/negative/non-USD available balances cannot be copied as spendable money. A credit limit is not cash. Current balance is displayed separately in the API projection and never substituted automatically for unknown available funds. [Plaid Accounts reference](https://plaid.com/docs/api/accounts/)
- Balance reads use `/accounts/balance/get`; the UI records fetch time rather than implying continuous freshness. Account IDs exposed to the UI are opaque hashes scoped to the linked Item.
- Review matches only the selected account's opaque ID. It cannot refresh a different account or a manually recorded source. Existing matching entries use `refresh_balance` with the already-reflected event IDs; new accounts use `upsert_money_source`. The preview uses the finance engine to show the before/after starting total. Both go through the existing local mock `finance.update` command and forecast flow. An accepted retry preserves its event ID; version conflicts require a new visible review. Manual/import matching and identities across relinking remain P1 work; confirm that newly added funds are not already recorded manually or from a previous linked Item.
- The connected-bank list shows each account's fetched balance and its saved budget balance separately. Names and masked endings label budget entries while that connection's metadata is available in memory. Sample cash is labeled separately in the starting-total breakdown. Previously overwritten balances are retained in the update audit; the user must review both accounts again to correct them, rather than silently changing saved financial records.
- The current planner remains fixed to **October 10, 2026**. Copying a bank balance is blocked when its fetch date in the case time zone differs from that planning date. The bank connection and read-only history still work. P1's current-date planning integration must replace this guard; do not misdate a newer bank balance to make the demo accept it.
- Transaction history is reduced, deduplicated, and displayed for review. Provider additions/modifications/removals update a staged map; the cursor advances only after all pages succeed. A pagination mutation restarts from the original cursor. Pending records superseded by posted records are removed. [Transactions sync reference](https://plaid.com/docs/api/products/transactions/)
- History is **not automatically committed as expenses, transfers, or aid receipts**. This avoids deducting spending already included in a refreshed balance or guessing that a deposit is disaster aid. Quantity/category matching, manual/import matching, restrictions, and transfer/withdrawal reconciliation need P1 integration and explicit resolution.
- Bank history and provider metadata are not appended to any chat. Only a confirmed normalized balance enters the browser-local finance ledger. Disconnect does not erase that accepted financial history or claim the account's funds became inaccessible.

## Remaining work

Complete a provider/browser verification pass. Exercise Link success/exit/error, account selection, delayed transaction preparation, add/modify/remove and pending-to-posted changes, retry/reload, server restart, private session isolation, balance review/conflicts, and disconnect. In particular, confirm checking and savings as separate entries, then review each again: the total should retain both and repeated reviews should not duplicate either. Previously overwritten entries need an explicit review of both accounts. Provider balances and transactions can be inconsistent in Sandbox; keep discrepancies visible. See [Plaid Sandbox](https://plaid.com/docs/sandbox/).

P1 must review/absorb the connector into its authenticated transport, protect durable token/cursor writes, add consent/disconnect lifecycle records and source timing to the agreed schema, use current-date forecasts, reconcile selected transaction imports through C08, and verify private bank data never reaches operator/shared knowledge projections. O01 remains `IN_PROGRESS`, and no production readiness is claimed.
