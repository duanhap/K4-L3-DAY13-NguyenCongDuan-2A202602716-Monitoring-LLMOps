"""Analyze logs.jsonl for incident investigation."""
from __future__ import annotations
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
logs = [
    json.loads(l)
    for l in (REPO_ROOT / "data" / "logs.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
]

responses = [r for r in logs if r.get("event") == "response_sent"]
requests  = [r for r in logs if r.get("event") == "request_received"]

print("=" * 70)
print("RESPONSE_SENT — sorted by latency DESC")
print("=" * 70)
for r in sorted(responses, key=lambda x: x.get("latency_ms", 0), reverse=True):
    print(
        f"  correlation_id : {r.get('correlation_id')}\n"
        f"  latency_ms     : {r.get('latency_ms')}\n"
        f"  ttft_ms        : {r.get('ttft_ms')}\n"
        f"  ts             : {r.get('ts')}\n"
        f"  feature        : {r.get('feature')}\n"
    )

print("=" * 70)
print("REQUEST_RECEIVED")
print("=" * 70)
for r in requests:
    print(
        f"  correlation_id : {r.get('correlation_id')}\n"
        f"  feature        : {r.get('feature')}\n"
        f"  ts             : {r.get('ts')}\n"
    )

# Pick the most anomalous request
if responses:
    worst = max(responses, key=lambda x: x.get("latency_ms", 0))
    print("=" * 70)
    print("MOST ANOMALOUS REQUEST (highest latency)")
    print("=" * 70)
    print(json.dumps(worst, indent=2))
