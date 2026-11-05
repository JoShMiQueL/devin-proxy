"""Smoke test a model lane against a running devin-proxy instance."""
import json
import sys
import urllib.request

model = sys.argv[1] if len(sys.argv) > 1 else "swe-2-flash"
prompt = sys.argv[2] if len(sys.argv) > 2 else "Reply with exactly: FLASH_OK"
port = sys.argv[3] if len(sys.argv) > 3 else "8390"

req = urllib.request.Request(
    f"http://127.0.0.1:{port}/v1/chat/completions",
    data=json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 64,
        "temperature": 0,
    }).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=120) as r:
    d = json.loads(r.read())
print("model asked:", model)
print("content   :", d["choices"][0]["message"].get("content"))
print("finish    :", d["choices"][0].get("finish_reason"))
print("usage     :", d.get("usage"))
