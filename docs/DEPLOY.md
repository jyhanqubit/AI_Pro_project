# Deploying ShockFlow AI to the web (Vercel + Render)

The app is two pieces:

- **Web** — the Next.js UI in `apps/web/` → deploy on **Vercel** (native Next.js host).
- **API** — the FastAPI server in `services/api/` → deploy on **Render** (or Railway/Fly).

> **Why not "all on Vercel"?** The API keeps the replay cutoff in server memory (a singleton
> `ReplayEngine`). Vercel's Python runtime is *serverless* — each request may hit a fresh instance,
> so the cutoff you set would be lost on the next call and the UI would break. The API therefore
> needs an **always-on server**. Render's free web service is the simplest fit.

Everything runs in offline **Demo Mode** (no API keys, no live collectors), so no secrets are needed.

---

## 1. Deploy the API on Render

1. Push this repo to GitHub (already done if you're reading this there).
2. Go to **render.com → New → Blueprint**, pick this repository. Render reads `render.yaml` and
   creates the `shockflow-api` web service:
   - build: `pip install -r requirements/serve.txt && pip install -e . --no-deps` (exact versions
     from the serving lock; the promoted model refuses to load under a scikit-learn other than the
     one it was fitted with, so the build never re-resolves)
   - start: `uvicorn services.api.app:app --host 0.0.0.0 --port $PORT`
3. Deploy. You'll get a URL like `https://shockflow-api.onrender.com`.
4. Check it: open `https://shockflow-api.onrender.com/v1/health` → should return JSON `{"status":"ok", ...}`.

> Free tier spins down when idle, so the **first request after a pause takes ~30–60s** (cold start).
> That's normal; subsequent requests are fast.

**Performance settings.** The blueprint sets `OMP_NUM_THREADS=1`: sklearn's `predict` otherwise
spawns OpenMP threads per request and they contend on a shared CPU (load test: saturated
throughput 105 → 138 req/s, `reports/v2/serving/load_test_configs.json`). It deliberately stays at
**one uvicorn worker**. The replay cutoff is a per-process singleton and the UI reads
`/v1/forecasts`, `/v1/events` and the explanation endpoint without passing a cutoff, so multiple
workers would answer with different cutoffs; a warm worker is also ~217 MB, so four would not fit
the 512 MB free instance. `--workers 4` reached ~700 req/s on a 4-CPU box, but only makes sense
once the cutoff is shared state (or sent on every call) and the instance has real cores.

*(No Blueprint? Create a Web Service manually with the same build/start commands and Python 3.11.)*

## 2. Deploy the Web UI on Vercel

1. Go to **vercel.com → Add New → Project**, import this repository.
2. Set **Root Directory = `apps/web`** (Vercel auto-detects Next.js there).
3. Add an environment variable:
   - `NEXT_PUBLIC_API_BASE = https://shockflow-api.onrender.com` (your Render URL from step 1)
4. Deploy. You'll get a URL like `https://shockflow.vercel.app`.

## 3. Open CORS from the API to your Vercel domain

The API only allows browsers from origins you list. In the Render dashboard for `shockflow-api`:

1. **Environment → add** `SHOCKFLOW_CORS_ORIGINS = https://shockflow.vercel.app`
   (use your real Vercel URL; comma-separate multiple, e.g. a preview domain too).
2. **Manual Deploy / Save** so the API restarts with the new allowlist.

Now open your Vercel URL — the operator screens should load live from the Render API.

---

## Notes

- **Order matters** only for the CORS step: deploy web first to learn its URL, then set
  `SHOCKFLOW_CORS_ORIGINS` on the API.
- **Local dev is unaffected** — the API still allows `http://localhost:3000` (and LAN `:3000`) via a
  built-in rule, so `make api` + `make web` keep working without any env vars.
- **Custom domain:** add it in Vercel, then append it to `SHOCKFLOW_CORS_ORIGINS` on Render.
- **Cost:** both free tiers are enough for a portfolio demo. The API cold-start pause is the only
  visible tradeoff of the free plan.
