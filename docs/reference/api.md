# HTTP API

Every route is under `/api` (`backend/src/pdf_assistant/api/`). The interactive OpenAPI page is
`/api/docs`, the schema `/api/openapi.json`. Routes marked "signed in" need the session cookie
`pdfa_session` and answer 401 without it; a user only ever sees their own PDFs, conversations and
messages, and another user's id answers 404. Errors are FastAPI's `{"detail": ...}`; the messages are
in Serbian, for the client to show as they are. Every `/api/` response carries
`Cache-Control: no-store`.

| Route | Access | Body or parameters | Answers |
|---|---|---|---|
| `GET /api/health` | open | | `{"status": "ok"}` |
| `GET /api/auth/user` | open | | the signed-in user, or `null` |
| `POST /api/auth/signup` | open | `email`, `password` (8 characters to 72 bytes) | 201 with the user and the session cookie; 403 when sign-up is closed; 409 when the address is taken |
| `POST /api/auth/signin` | open | `email`, `password` | the user and the session cookie; 401 on a wrong address or password |
| `POST /api/auth/signout` | open | | 204, the cookie removed |
| `GET /api/pdfs` | signed in | | the user's PDFs |
| `POST /api/pdfs` | signed in | multipart `file` | 201 with the PDF in `processing`; 400 when not a PDF; 413 when larger than `MAX_UPLOAD_MB`; 503 when PDF storage fails |
| `GET /api/pdfs/{pdf_id}` | signed in | | one PDF with its status (`processing`, `ready`, `failed`) and error |
| `GET /api/pdfs/{pdf_id}/file` | signed in | | the PDF itself, `application/pdf`, shown inline |
| `DELETE /api/pdfs/{pdf_id}` | signed in | | 204; the rows, the file and the vectors go |
| `GET /api/pdfs/{pdf_id}/conversations` | signed in | | the PDF's conversations |
| `POST /api/pdfs/{pdf_id}/conversations` | signed in | | 201 with a new conversation and the components drawn for it |
| `DELETE /api/conversations/{conversation_id}` | signed in | | 204 |
| `POST /api/conversations/{conversation_id}/messages` | signed in | `content`, the question, up to 4000 characters | a stream of newline-delimited JSON events, below |
| `PUT /api/messages/{message_id}/vote` | signed in | `score`: `1`, `-1`, or `0` to withdraw | the answer with its vote; 400 for a question |
| `GET /api/scores` | signed in | | per kind (`llm`, `retriever`, `memory`), each component's `label`, `active`, `up`, `down`, `satisfaction` and `weight`, counted over all users |
| `GET /{path}` | open | | the built client: a file under `CLIENT_DIR` when it exists, else `index.html`; 404 under `api/` and when the client is not built |

## The answer stream

`POST /api/conversations/{id}/messages` answers with one JSON object per line:

```
{"type": "start", "user_message": Message, "title": ...}
{"type": "delta", "text": "..."}            repeated
{"type": "end", "message": Message}          the saved answer with its sources
{"type": "error", "detail": "..."}          instead of "end"; nothing is saved
```

The client reads it with `client/src/lib/api/ndjson.ts`; citations `[n]` in the answer point at the
sources, each with its page.
