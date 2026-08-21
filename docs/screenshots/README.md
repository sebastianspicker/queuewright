# Screenshot maintenance

The repository contains:

| File | Viewport | View |
|---|---:|---|
| `studio-readiness.png` | 1600 by 1000 | Readiness and limitations |
| `studio-mobile.png` | 390 by 844 at device scale factor 2 | Mobile service structure |

The current files show the fictional university template and local compilation
state. They contain no tenant connection or live data.

The screenshots are maintained product documentation. Browser automation is not
part of this repository's test or release workflow.

## Review

Before replacing the checked-in files:

1. Run `npm run build`.
2. Confirm that the Python service and Vite use loopback addresses.
3. Check the desktop and mobile images for clipping, stale labels, private
   content, and unrelated desktop elements.
4. Confirm that the project data is fictional.
5. Run `python3 scripts/verify_repo.py` from the repository root.

Screenshots document visible states. Python contracts cover the local API and
connected-control boundaries.
