# Deploying to Cloudflare Pages

GitHub Pages caps single files at ~100 MB and has stricter bandwidth limits.
Cloudflare Pages is free, supports unlimited bandwidth, and serves large
trip-tier `.bin` files happily. The same GitHub repo can be the source for
both — auto-deploy on every push to `main`.

## One-time setup (≈ 5 minutes)

1. Open <https://dash.cloudflare.com/> and create a free account (just an
   email; no credit card).
2. In the dashboard left nav, click **Workers & Pages** → **Create
   application** → **Pages** → **Connect to Git**.
3. Authorize Cloudflare to read your GitHub. On the repo picker, choose
   `NirmitSachde/the-carbon-clock-manhattan` and click **Begin setup**.
4. **Project name**: `the-carbon-clock-manhattan` (anything you like — this
   becomes the subdomain: `<name>.pages.dev`).
   **Production branch**: `main`.
5. Build settings:
   - **Framework preset**: *None*
   - **Build command**: leave empty (it's a static site)
   - **Build output directory**: `/` (the repo root is the site)
6. Click **Save and Deploy**. First build runs in ~30 seconds.

When the build finishes you'll have a live URL like
`https://the-carbon-clock-manhattan.pages.dev/`. Every subsequent `git push`
to `main` triggers an auto-deploy with cache busting.

## Why use this instead of (or alongside) GitHub Pages

| | GitHub Pages | Cloudflare Pages |
|---|---|---|
| File-size hint | 100 MB | up to 25 MB per file, but you can split |
| Total bandwidth | 100 GB / month | **unlimited** |
| Build time after push | ~30 s | ~30 s |
| Custom domain | free | free |
| CDN region count | one (Fastly) | 300+ |

For our case the 500 K and 2 M trip tiers exceed 25 MB raw — they're stored
split into shards or just hosted from GitHub Pages while smaller tiers are
served by both. The visualization tries Cloudflare first; GitHub Pages is
the fallback.

## Pointing the site at Cloudflare

Once the Cloudflare URL is live, no code changes are needed — the same
`index.html` works on both hosts. Share whichever URL you prefer:

- `https://the-carbon-clock-manhattan.pages.dev/`        ← Cloudflare
- `https://nirmitsachde.github.io/the-carbon-clock-manhattan/` ← GitHub Pages
