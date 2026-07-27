# Screenshot maintenance

The repository contains:

| File | Viewport | View |
|---|---:|---|
| `studio-readiness.png` | 1600 by 1000 | Readiness and limitations |
| `studio-mobile.png` | 390 by 844 at device scale factor 2 | Mobile service structure |

The current files show the fictional university template and local compilation
state. They contain no tenant connection or live data.

## Capture

Install frontend dependencies and Playwright Chromium:

```bash
cd studio-ui
npm ci
npx playwright install chromium
```

Start the Python service from the repository root:

```bash
python3 -m queuewright_studio
```

Start Vite in another terminal:

```bash
cd studio-ui
npm run dev
```

Run the capture script from `studio-ui/`:

```bash
node ../scripts/capture_studio_screenshots.mjs
```

The script uses `http://127.0.0.1:5173` by default. Set `STUDIO_URL` only when
the same application is available at another local browser URL:

```bash
STUDIO_URL=http://127.0.0.1:5173 \
  node ../scripts/capture_studio_screenshots.mjs
```

## Review

Before replacing the checked-in files:

1. Run `npm run test` and `npm run build`.
2. Confirm that the Python service and Vite use loopback addresses.
3. Check the desktop and mobile images for clipping, stale labels, private
   content, and unrelated desktop elements.
4. Confirm that the project data is fictional.
5. Run `python3 scripts/verify_repo.py` from the repository root.

Screenshots document visible states. They do not replace interaction,
accessibility, API-boundary, or cross-browser tests.
