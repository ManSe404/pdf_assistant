#!/usr/bin/env bash
# Live end-to-end run against real model providers: the one-image stack in Docker, one PDF upload,
# two questions with citations checked. Refuses to start without model keys in .env (ANTHROPIC_API_KEY
# + OPENAI_API_KEY for the default setup, or a provider setup from the README).
#
#   backend/bin/e2e_live.sh [report.json]        # default report: backend/data/e2e/e2e-<date>.json (git-ignored)
#
# Exit 0 when the PDF is ready and both answers carry a citation. Nothing tracked by git is written.
set -euo pipefail
cd "$(dirname "$0")/../.."
REPORT="${1:-backend/data/e2e/e2e-$(date +%Y%m%d-%H%M%S).json}"
mkdir -p "$(dirname "$REPORT")"
BASE="${E2E_BASE_URL:-http://localhost:8000}"
[ -f .env ] || { echo "no .env next to docker-compose.yml: put the model keys there first"; exit 2; }
grep -qE '^(ANTHROPIC_API_KEY|OPENAI_API_KEY|AZURE_OPENAI_API_KEY|ANTHROPIC_FOUNDRY_API_KEY|CHAT_PROVIDER)=' .env \
  || { echo "no model keys in .env; refusing a fake run"; exit 2; }
echo "== docker compose up"
docker compose up -d --build
for _ in $(seq 1 60); do curl -sf -m 3 "$BASE/api/health" >/dev/null && break; sleep 3; done
curl -sf -m 3 "$BASE/api/health" >/dev/null || { echo "api not healthy at $BASE"; docker compose logs --tail 40; exit 1; }

E2E_BASE_URL="$BASE" E2E_REPORT="$REPORT" python3 - <<'PY'
import http.cookiejar, json, os, sys, time, urllib.request, uuid
from pathlib import Path

base, report_path = os.environ["E2E_BASE_URL"], os.environ["E2E_REPORT"]
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))  # session cookie
report = {"base": base, "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "questions": []}

def call(method, path, body=None, raw=None, content_type=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(base + path, data=data, method=method)
    if content_type: request.add_header("Content-Type", content_type)
    elif body is not None: request.add_header("Content-Type", "application/json")
    with opener.open(request, timeout=600) as response:
        text = response.read().decode()
    return json.loads(text) if text.startswith(("{", "[")) else text

call("POST", "/api/auth/signup", {"email": f"e2e-{uuid.uuid4().hex[:8]}@example.com", "password": "e2e-" + uuid.uuid4().hex})

# A small real PDF with a text layer, built here so the run needs no fixture.
def make_pdf(lines):
    ops = "BT /F1 11 Tf 14 TL 50 750 Td " + " ".join(f"({l.replace('(', '').replace(')', '')}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out)); out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    return out + f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()

pdf = make_pdf(["Lease agreement", "The deposit is two monthly rents.", "The notice period is sixty days.", "Payment is due by the fifth of the month."])
boundary = "----e2e" + uuid.uuid4().hex
body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"lease.pdf\"\r\nContent-Type: application/pdf\r\n\r\n").encode() + pdf + f"\r\n--{boundary}--\r\n".encode()
uploaded = call("POST", "/api/pdfs", raw=body, content_type=f"multipart/form-data; boundary={boundary}")
pdf_id = uploaded["id"]
deadline, started = time.time() + 600, time.time()
while True:
    status = call("GET", f"/api/pdfs/{pdf_id}")
    if status.get("status") in ("ready", "error") or time.time() > deadline:
        break
    time.sleep(3)
report["pdf"] = status
report["indexing_seconds"] = round(time.time() - started, 1)
conversation = call("POST", f"/api/pdfs/{pdf_id}/conversations")
for question in ("How big is the deposit?", "And the notice period?"):
    t0 = time.time()
    stream = call("POST", f"/api/conversations/{conversation['id']}/messages", {"content": question})
    events = [json.loads(line) for line in str(stream).splitlines() if line.strip()]
    answer = "".join(e.get("text", "") for e in events if e["type"] == "delta")
    end = next((e for e in events if e["type"] in ("end", "error")), {})
    report["questions"].append({"question": question, "answer": answer, "citations": end.get("citations", []),
                                "error": end.get("detail"), "seconds": round(time.time() - t0, 1)})
ok = status.get("status") == "ready" and all(q["citations"] for q in report["questions"])
report["ok"] = ok
Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({"pdf": status.get("status"), "indexing_seconds": report["indexing_seconds"], "ok": ok}, indent=1))
for q in report["questions"]:
    print(f"\nQ: {q['question']}\nA: {q['answer'][:300]}\ncitations: {[(c.get('page')) for c in q['citations']]}  error: {q['error']}")
print(f"\nreport: {report_path}")
sys.exit(0 if ok else 1)
PY
