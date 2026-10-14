# Company Brain UI

Next.js 15 (App Router). Talks only to the Python API.

```bash
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build && npm start   # :3000
```

Pages: Overview (`/`), Ask (`/ask`, `?q=` prefills), Graph (`/graph`). Paste the judges' token in the top bar to enable writes; without it the app runs in anonymous mode. `?debug=1` shows raw packs and the verifier report.
