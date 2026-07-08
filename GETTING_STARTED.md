# BasisPulse — Getting Started

A guide for people **outside the project** who want to run BasisPulse
themselves and, if they want, upgrade to Pro. No coding experience assumed —
every command below is copy-paste.

> ⚠️ Educational analytics, not investment advice. See the main
> [README](README.md) for what the product does and how the Radar Score
> works.

---

## 1. What you'll need

- A computer running **Windows, macOS, or Linux**.
- **Python 3.10 or newer** installed. Check with:
  ```
  python3 --version
  ```
  (On Windows, use `py --version` instead. If neither command is found,
  install Python from [python.org/downloads](https://www.python.org/downloads/)
  first — tick **"Add Python to PATH"** during setup.)
- **Git** installed (or just use the "Download ZIP" option in step 2 if you'd
  rather not install Git).
- A terminal:
  - **macOS**: the built-in **Terminal** app.
  - **Windows**: **PowerShell** (search for it in the Start menu — not the
    Python REPL, not the old `cmd.exe`).
  - **Linux**: whatever terminal you normally use.

---

## 2. Get the code

**Option A — Git (recommended):**

```
git clone https://github.com/mrmclaude1/Side-hustle-2026.01.git
cd Side-hustle-2026.01
git checkout claude/500-to-100k-growth-byz51k
```

> The third line matters right now — the BasisPulse app currently lives on
> that branch, not on `main`. (Once it's merged, `git checkout` won't be
> needed and this doc will be updated.)

**Option B — No Git:** on the
[repository page](https://github.com/mrmclaude1/Side-hustle-2026.01), switch
the branch dropdown to `claude/500-to-100k-growth-byz51k`, click the green
**Code** button → **Download ZIP**, then unzip it and open a terminal in that
folder.

**Windows note:** if PowerShell opens directly into
`C:\Windows\System32`, you'll get "Permission denied" errors. Run `cd ~`
first to move to your home folder, *then* clone/unzip there.

---

## 3. Install and run

**macOS / Linux — one command:**

```
./run.sh
```

This creates an isolated Python environment, installs the two dependencies
(FastAPI + Uvicorn), and starts the server.

**Windows (PowerShell):**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --port 8000
```

**Either way**, once it's running you'll see a line like:

```
Uvicorn running on http://0.0.0.0:8000
```

Leave that terminal window open — it's your running server. Press
`Ctrl+C` in it any time to stop.

---

## 4. Open the app

In a browser, go to:

- **http://localhost:8000/** — the marketing/landing page
- **http://localhost:8000/app** — the actual scanner dashboard

The first time you open `/app`, a **"Start here" tour** pops up explaining
the table, the score, alerts, and cross-exchange view — click through it (or
reopen it anytime with the **?** button in the header).

A pill near the top-right reads either:
- **● LIVE** — pulling real, current market data, or
- **DEMO SNAPSHOT** — your network can't reach the exchange APIs, so it's
  showing a bundled sample instead. The app still fully works in this mode;
  it's just not real-time.

---

## 5. Becoming a Pro user

There are two situations, depending on whether you're just running this on
your own machine, or you're the one operating a public version for other
people.

### If someone else is hosting BasisPulse for you

1. Open the dashboard, scroll to the **Pro** section, and click **Get Pro**
   on the pricing card. That opens a secure Stripe checkout page.
2. Subscribe with a card. Stripe handles payment — BasisPulse never sees or
   stores your card details.
3. The site operator will send you your **Pro API key** (a string starting
   with `bp_`) — today that's a short manual step on their end, usually
   within a day of your payment.
4. Paste that key into the **Pro** section's "Paste your API key" field and
   click **Use key**. The "plan" pill in the header should now read **PRO**,
   and you'll get deeper scans, unlimited alerts, CSV export, and higher API
   rate limits.

### If you're running your own copy (self-hosting)

Pro on your own instance works without paying anyone — you're the operator.

1. **Get a free API key** (optional — only needed if you want to test the
   Pro upgrade path, or use the API directly):
   ```
   curl -X POST http://localhost:8000/api/keys
   ```
   This returns a JSON object with a `key` starting with `bp_`.

2. **Upgrade a key to Pro yourself.** Set an admin token *before* starting
   the server, then restart it (`.env.example` lists every variable
   BasisPulse understands, as a reference — it's not loaded automatically,
   so set it directly in your terminal):
   ```
   # macOS/Linux
   export BASISPULSE_ADMIN_TOKEN=some-long-random-string
   ./run.sh
   ```
   ```powershell
   # Windows PowerShell
   $env:BASISPULSE_ADMIN_TOKEN="some-long-random-string"
   py -m uvicorn app.main:app --port 8000
   ```
   Then, in a second terminal window (leave the server running), mint a Pro
   key:
   ```
   curl -X POST http://localhost:8000/api/keys \
     -H "X-Admin-Token: some-long-random-string" \
     -H "Content-Type: application/json" \
     -d '{"plan":"pro","label":"me"}'
   ```
   Paste the returned key into the dashboard's Pro section as above.

3. **To actually charge real customers**, you'll additionally wire up
   Stripe (product, checkout link, webhook) and deploy the app somewhere
   public instead of `localhost`. That whole process — with exact
   click-by-click steps — is documented in [`DEPLOY.md`](DEPLOY.md).

---

## 6. Common problems

| Symptom | Fix |
|---|---|
| `git: command not found` | Install Git, or use "Download ZIP" (step 2, option B) instead. |
| PowerShell shows "Permission denied" cloning/installing | You're in `C:\Windows\System32`. Run `cd ~` first, then retry. |
| You typed a command but nothing happened | Make sure you pressed **Enter**, and that you're in PowerShell/Terminal — not inside the Python interpreter (its prompt looks like `>>>`; if you see that, type `exit()` first). |
| Browser says "site can't be reached" | The server isn't running, or you closed its terminal window. Re-run the step-3 command and leave that window open. |
| Dashboard loads but the table is empty | Refresh once — the very first load has nothing to show until a scan completes. If it's still empty after a few seconds, check the terminal window for a red error line. |
| Pill says "DEMO SNAPSHOT" instead of "LIVE" | Your network can't reach the exchange APIs (common on restricted work/school networks or if an exchange blocks your region). The app is working correctly — it's just showing sample data instead of live prices. |

---

## 7. Getting help

Open an issue on the
[GitHub repository](https://github.com/mrmclaude1/Side-hustle-2026.01/issues)
with what you ran, what you expected, and what happened instead (a
screenshot of the terminal helps a lot).
