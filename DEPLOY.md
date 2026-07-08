# BasisPulse — Deployment Runbook

Exact steps from "code in a GitHub repo" to "live product on your own domain
taking payments." Total cost: **~$12/yr (domain) + ~$7–8/mo (hosting)** — well
inside the $500 budget. Time: about an hour, most of it waiting on DNS/Stripe.

Everything the app needs is configured by environment variables — there are
**no code changes** in this runbook.

| Env var | What it does | Set it to |
|---|---|---|
| `BASISPULSE_DB` | SQLite path (history, alerts, API keys) | `/data/basispulse.db` (on the persistent disk) |
| `BASISPULSE_ADMIN_TOKEN` | Protects manual key provisioning | a long random string (`openssl rand -hex 24`) |
| `BASISPULSE_PRO_PRICE` | Price shown on pricing cards | `19` (must match your Stripe price) |
| `BASISPULSE_CHECKOUT_URL` | Stripe Payment Link behind "Get Pro" | from Step 4 |
| `STRIPE_WEBHOOK_SECRET` | Verifies Stripe webhooks (**required in prod**) | from Step 5 |
| `BASISPULSE_WEBHOOK_URL` | Alert pushes to Discord/Slack (optional) | your incoming-webhook URL |

`PORT` is set by the host automatically; the Dockerfile already honors it.

---

## Step 0 — Merge to main

Deploy from `main` so future pushes to the branch don't auto-deploy mid-review.

1. Open the repo's pull request for `claude/500-to-100k-growth-byz51k`.
2. Mark it **Ready for review** → **Merge**.

(You *can* point the host at the feature branch instead — everything below
works the same — but main is the sane default.)

## Step 1 — Buy the domain (~$12/yr)

1. Go to a registrar — **Namecheap**, **Porkbun**, or **Cloudflare Registrar**
   (cheapest at cost, but requires using Cloudflare DNS).
2. Search **`basispulse.com`** — it showed no DNS record or site when checked,
   but the registrar's search is the final word. If it's gone, `basispulse.io`
   / `.app` / `.xyz` are fine fallbacks (update nothing in code — the app
   never hardcodes the domain).
3. Buy it. Skip every upsell (email, SSL, "premium DNS") — you need none of it.

## Step 2 — Deploy on Render (~$7/mo + $0.25/mo disk)

Render is the recommended host: Docker support, persistent disks for SQLite,
free TLS, custom domains on the cheapest paid tier.

1. Sign up at **render.com** → **Sign in with GitHub** → authorize access to
   the repo.
2. **New → Web Service** → select the repo, branch `main`.
3. Render auto-detects the **Dockerfile** — keep runtime = Docker. If asked
   for a start command, leave it empty (the image's CMD already runs
   `uvicorn` on `$PORT`).
4. Instance type: **Starter** (~$7/mo). Do **not** use the free tier — free
   instances spin down when idle, which kills the snapshot cron, resets the
   in-memory cache, and makes first loads take ~50s.
5. Before the first deploy, open **Advanced**:
   - **Add Disk**: name `data`, mount path **`/data`**, size **1 GB**
     (~$0.25/mo). SQLite must live on a disk or history/keys are wiped on
     every deploy.
   - **Environment variables** — add:
     ```
     BASISPULSE_DB=/data/basispulse.db
     BASISPULSE_ADMIN_TOKEN=<paste output of: openssl rand -hex 24>
     BASISPULSE_PRO_PRICE=19
     ```
     (Stripe vars come later; the app runs fine without them.)
   - **Health check path**: `/api/health`
6. **Create Web Service** → wait for the build (~2–3 min).
7. Verify on the `*.onrender.com` URL Render gives you:
   - `/` — landing page renders
   - `/app` — dashboard shows live data (pill says **● LIVE**, not DEMO —
     the exchange APIs are reachable from Render)
   - `/api/health` — returns `{"status":"ok", ...}`

> **Railway / Fly alternative:** both work with the same Dockerfile —
> Railway: New Project → Deploy from GitHub repo → add a volume at `/data` →
> same env vars. Fly: `fly launch` → `fly volumes create data` → mount in
> `fly.toml`. The rest of this runbook is host-agnostic.

## Step 3 — Snapshot cron (builds trends & fires alerts)

History, Δ-score, sparklines and alert evaluation all happen when
`GET /api/snapshot` is called. Schedule it every 15 minutes:

**Easiest (free):** [cron-job.org](https://cron-job.org) → create account →
**Create cronjob** → URL `https://<your-app>.onrender.com/api/snapshot` →
every 15 minutes → save. Done.

**Or on Render:** New → **Cron Job** →
command `curl -fsS https://<your-app>.onrender.com/api/snapshot` →
schedule `*/15 * * * *` (small extra monthly cost).

Within an hour the dashboard's Δ column and sparklines come alive.

## Step 4 — Point the domain at Render

1. Render dashboard → your service → **Settings → Custom Domains** →
   **Add** `basispulse.com` and `www.basispulse.com`.
2. Render shows you the records to create. At your registrar's DNS panel:
   - `www` → **CNAME** → `<your-app>.onrender.com`
   - apex `basispulse.com` → **A** record to the IP Render displays
     (or ALIAS/ANAME → `<your-app>.onrender.com` if your registrar supports it)
3. Wait for DNS (minutes to an hour). Render provisions TLS automatically —
   both hosts go green in the dashboard.
4. Check `https://basispulse.com` loads the landing page. The OG/canonical
   tags pick up the domain automatically from the request — nothing to edit.

## Step 5 — Stripe (take payments)

### 5a. Product & Payment Link

1. Create an account at **stripe.com** → complete business activation
   (identity + bank details; payouts unlock when approved, but you can build
   everything in **Test mode** immediately — use the Test/Live toggle, top
   right).
2. **Product catalog → Add product**: name `BasisPulse Pro`, recurring,
   **$19 / month** (this must match `BASISPULSE_PRO_PRICE`).
3. **Payment Links → New** → pick the BasisPulse Pro price → after payment,
   show the confirmation page → **Create link**. Copy the
   `https://buy.stripe.com/…` URL.
4. In Render → Environment: add
   ```
   BASISPULSE_CHECKOUT_URL=https://buy.stripe.com/<your-link>
   ```
   Save (Render redeploys). "Get Pro" buttons on the landing page and
   dashboard now open your checkout.

### 5b. Webhook (auto-upgrades keys)

1. Stripe → **Developers → Webhooks → Add endpoint**.
2. Endpoint URL: `https://basispulse.com/api/billing/webhook`
3. Events: `checkout.session.completed`,
   `customer.subscription.created`, `customer.subscription.updated`,
   `customer.subscription.deleted`.
4. Create, then copy the **Signing secret** (`whsec_…`).
5. In Render → Environment: add
   ```
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```
   **Required in production** — without it the endpoint accepts unsigned
   events.

### 5c. How a customer becomes Pro

Two paths, both already wired:

- **Existing key holders** (cleanest): they grab a free key
  (`POST /api/keys`), then check out via your Payment Link with the key
  attached: `https://buy.stripe.com/<link>?client_reference_id=bp_theirkey`.
  The webhook upgrades that exact key to Pro. (You can put this
  parameterized link in the post-signup email/docs.)
- **Straight purchase**: they just pay. The webhook creates a Pro key bound
  to the Stripe customer. Look it up and email it to them:
  ```bash
  # from the Render shell (the slim image has no sqlite3 CLI, so use Python):
  python3 -c "import sqlite3; [print(r) for r in sqlite3.connect('/data/basispulse.db').execute(
    'SELECT key, plan, stripe_customer_id FROM api_keys ORDER BY created_ts DESC LIMIT 5')]"
  ```
  A few manual emails a week is fine at this stage; automate later.

Comp yourself / a friend a Pro key anytime:

```bash
curl -X POST https://basispulse.com/api/keys \
  -H "X-Admin-Token: $BASISPULSE_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"plan":"pro","label":"founder"}'
```

### 5d. Test the loop (Test mode)

1. Toggle Stripe to **Test mode**, make a *test* Payment Link + webhook the
   same way (test signing secret in a temporary env var), pay with card
   `4242 4242 4242 4242`.
2. Confirm the webhook shows `200` in Stripe's dashboard and a key got
   upgraded/created.
3. Cancel the test subscription → confirm the webhook downgrade fires.
4. Switch everything to Live values.

## Step 6 — Optional: alert pushes to Discord

1. In your Discord server: **Server Settings → Integrations → Webhooks →
   New Webhook** → copy URL.
2. Render env: `BASISPULSE_WEBHOOK_URL=https://discord.com/api/webhooks/…`
3. Every snapshot that trips a rule now posts to the channel. (Slack
   incoming webhooks or any HTTP endpoint work identically.)

## Step 7 — Post-launch checklist

- [ ] `https://basispulse.com` and `/app` load over TLS, pill shows **LIVE**
- [ ] Δ column + sparklines populate after ~1h of snapshot cron
- [ ] Share the URL in a private Discord/Slack — link preview shows the
      OG image
- [ ] Test-mode Stripe purchase upgraded a key; cancel downgraded it
- [ ] `BASISPULSE_ADMIN_TOKEN` is random and saved in your password manager
- [ ] `STRIPE_WEBHOOK_SECRET` is set (webhook rejects unsigned posts)
- [ ] Uptime monitor (free: UptimeRobot) pointed at `/api/health`

## Monthly cost recap

| Item | Cost |
|---|---|
| Domain | ~$1/mo amortized |
| Render Starter + 1 GB disk | ~$7.25/mo |
| Cron (cron-job.org) + UptimeRobot | $0 |
| Stripe | 2.9% + 30¢ per transaction, no fixed fee |
| **Total fixed** | **~$8–9/mo** |

First paying customer at $19/mo covers the entire infrastructure.
