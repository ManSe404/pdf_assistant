# Client

The web client in `client/`: a SvelteKit single-page app (Svelte 5 runes, Tailwind 4, pdf.js,
chart.js, marked, DOMPurify) in Serbian. It has no server of its own: in the Docker image, or
whenever `client/build/` exists, the [backend](backend.md) serves its built files; in development
Vite serves it and forwards `/api` to the backend.

## What it does

| Page | Path | What the user does there |
|---|---|---|
| Sign in, sign up | `/auth/signin`, `/auth/signup` | enter e-mail and password; `?next=` brings the user back to the page they came from |
| Documents | `/documents` | the user's PDFs with status, size and date; delete; polls every 2 s while one is processing |
| Upload | `/documents/new` | pick a PDF, see the upload progress, go back to the list |
| Document | `/documents/[id]` | the conversation and the PDF side by side (two tabs below 1024 px), conversations, streamed answers, sources, votes |
| Scores | `/scores` | the experiment's components with votes, satisfaction and chance, as a bar chart |

`/` redirects to `/documents`. The root layout (`src/routes/+layout.ts`) sends a signed-out user to
the sign-in page and a signed-in user away from it; `src/hooks.client.ts` sends any 401 outside the
sign-in forms back to sign-in and shows 5xx and network errors as alerts.

## How to run it

Node 24 (`client/.nvmrc`); `engines` allows 22.17+, 24 and 26+, and `engine-strict=true`
(`client/.npmrc`) makes `npm ci` refuse Node 25.

| Command (in `client/`) | What it does |
|---|---|
| `npm install` or `npm ci` | install the dependencies |
| `npm run dev` | Vite on `http://localhost:5173`, `/api` forwarded to `API_URL`. Vite listens on `localhost` only, which can be the IPv6 `::1` alone, so `127.0.0.1:5173` may not answer. |
| `npm run build` | the static app into `client/build/`, with `index.html` as the fallback for every route |
| `npm run preview` | serve the build, with the same `/api` forwarding |
| `npm run check`, `npm run lint`, `npm test` | svelte-check, Prettier and ESLint, Vitest |

A build rewrites `client/build/index.html` and `client/build/_app/version.json`, which are tracked
by git ([codebase](../codebase.md)), so `git status` shows them changed after every build.

## Configuration

One variable, read by `client/vite.config.ts` for the dev server and `vite preview` only:
`API_URL` (default `http://127.0.0.1:8000`). The built app calls `/api` on its own origin and has no
settings; the upload limit of 50 MB is fixed in `src/lib/api/upload.ts`.

## Code

| Folder | What is there |
|---|---|
| `src/routes/` | the pages above; they hold layout and call the state classes |
| `src/lib/api/` | `client.ts` (the one `fetch` wrapper, timeouts, 401 and 5xx hooks), `upload.ts` (XMLHttpRequest for progress), `ndjson.ts` (stream reader), `errors.ts` (Serbian messages), `types.ts` (the backend's shapes) |
| `src/lib/state/` | runes classes: `auth`, `documents`, `chat` (one `ChatSession` per document page), `alerts` |
| `src/lib/components/` | shared components; `chat/` for messages, sources and citations, `pdf/` for the pdf.js viewer |
| `src/lib/markdown/` | answers: Markdown to HTML with marked, `[n]` to buttons, then DOMPurify |
| `src/lib/format.ts` | Serbian formatting of dates, sizes and shares |

## Contracts

- **HTTP API** under `/api` on the same origin, with the httpOnly session cookie the backend sets
  ([HTTP API](../api.md)). The response shapes are written out in `src/lib/api/types.ts`; they mirror
  `backend/src/pdf_assistant/api/schemas.py` by hand, and nothing checks that the two agree.
- **The answer stream**: newline-delimited JSON events `start`, `delta`, `end` or `error`, read by
  `src/lib/api/ndjson.ts`.
- **The PDF file**: `GET /api/pdfs/{id}/file`, loaded by pdf.js in
  `src/lib/components/pdf/PdfViewer.svelte`.

## Tests

Vitest over `src/**/*.test.ts`: the error messages (`errors.test.ts`), the NDJSON reader
(`ndjson.test.ts`) and answer rendering with citations (`answer.test.ts`). The pages and components
have no tests.
