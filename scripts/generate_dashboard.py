"""
Generate dashboard HTML from data/logs.jsonl.
Usage: python scripts/generate_dashboard.py
Opens dashboard.html in the default browser automatically.
"""
from __future__ import annotations

import json
import math
import os
import sys
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
OUT_PATH = REPO_ROOT / "dashboard.html"


# ── helpers ────────────────────────────────────────────────────────────────────

def load_logs(time_range_minutes: int = 60) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    records = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # Filter to last N minutes based on dashboard contract
    if records and time_range_minutes > 0:
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - time_range_minutes * 60
        filtered = []
        for r in records:
            ts = r.get("ts", "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.timestamp() >= cutoff:
                    filtered.append(r)
            except Exception:
                filtered.append(r)  # keep if can't parse timestamp
        # If filter removes everything (e.g. old log file), fall back to all records
        return filtered if filtered else records

    return records


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = (len(sorted_v) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_v) - 1)
    return round(sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (idx - lo), 2)


def bucket_by_minute(records: list[dict], field: str) -> tuple[list[str], list[float]]:
    """Group sum of `field` by minute, returns (labels, values)."""
    buckets: dict[str, float] = defaultdict(float)
    for r in records:
        ts = r.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            key = dt.strftime("%H:%M")
        except Exception:
            key = "?"
        val = r.get(field, 0) or 0
        buckets[key] += val
    if not buckets:
        return [], []
    labels = sorted(buckets)
    return labels, [round(buckets[k], 6) for k in labels]


def count_by_minute(records: list[dict]) -> tuple[list[str], list[int]]:
    buckets: dict[str, int] = defaultdict(int)
    for r in records:
        ts = r.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            key = dt.strftime("%H:%M")
        except Exception:
            key = "?"
        buckets[key] += 1
    if not buckets:
        return [], []
    labels = sorted(buckets)
    return labels, [buckets[k] for k in labels]


# ── compute metrics ─────────────────────────────────────────────────────────────

def compute(logs: list[dict]) -> dict:
    response_logs = [r for r in logs if r.get("event") == "response_sent"]
    request_logs  = [r for r in logs if r.get("event") == "request_received"]
    failed_logs   = [r for r in logs if r.get("event") == "request_failed"]

    latencies = [r["latency_ms"] for r in response_logs if "latency_ms" in r]
    ttfts     = [r["ttft_ms"]    for r in response_logs if "ttft_ms" in r]

    p50  = percentile(latencies, 50)
    p95  = percentile(latencies, 95)
    p99  = percentile(latencies, 99)
    tp95 = percentile(ttfts, 95)

    req_labels, req_counts = count_by_minute(request_logs)
    cost_labels, cost_vals = bucket_by_minute(response_logs, "cost_usd")
    total_cost = round(sum(r.get("cost_usd", 0) or 0 for r in response_logs), 6)

    tokens_in  = sum(r.get("tokens_in",  0) or 0 for r in response_logs)
    tokens_out = sum(r.get("tokens_out", 0) or 0 for r in response_logs)

    quality_scores = [r["quality_score"] for r in response_logs if "quality_score" in r]
    mean_quality = round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else 0.0

    total_req   = len(request_logs)
    total_fail  = len(failed_logs)
    error_rate  = round(total_fail / total_req * 100, 2) if total_req else 0.0
    tool_success_logs = [r for r in response_logs if r.get("tool_success") is not None]
    tool_ok = sum(1 for r in tool_success_logs if r.get("tool_success") is True)
    retrieval_success = round(tool_ok / len(tool_success_logs) * 100, 1) if tool_success_logs else 100.0

    # latency over time for chart
    lat_labels, lat_p95_vals = [], []
    lat_buckets: dict[str, list[float]] = defaultdict(list)
    for r in response_logs:
        ts = r.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            key = dt.strftime("%H:%M")
        except Exception:
            key = "?"
        if "latency_ms" in r:
            lat_buckets[key].append(r["latency_ms"])
    for k in sorted(lat_buckets):
        lat_labels.append(k)
        lat_p95_vals.append(percentile(lat_buckets[k], 95))

    return dict(
        p50=p50, p95=p95, p99=p99, tp95=tp95,
        lat_labels=lat_labels, lat_p95_vals=lat_p95_vals,
        req_labels=req_labels, req_counts=req_counts,
        total_req=total_req, total_fail=total_fail, error_rate=error_rate,
        retrieval_success=retrieval_success,
        cost_labels=cost_labels, cost_vals=cost_vals, total_cost=total_cost,
        tokens_in=tokens_in, tokens_out=tokens_out,
        quality_scores=quality_scores, mean_quality=mean_quality,
    )


# ── HTML template ───────────────────────────────────────────────────────────────

HTML_TMPL = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>K4-L3B Day 13 — Monitoring & LLMOps Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:16px; }}
  h1   {{ font-size:1.3rem; color:#7dd3fc; margin-bottom:4px; }}
  .meta {{ font-size:.8rem; color:#94a3b8; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
  .card {{ background:#1e293b; border-radius:10px; padding:16px; }}
  .card h2 {{ font-size:.9rem; color:#94a3b8; margin:0 0 6px; text-transform:uppercase; letter-spacing:.05em; }}
  .kpi  {{ display:flex; gap:24px; flex-wrap:wrap; margin-bottom:10px; }}
  .kpi-item {{ text-align:center; }}
  .kpi-val  {{ font-size:1.6rem; font-weight:700; color:#38bdf8; }}
  .kpi-lbl  {{ font-size:.7rem; color:#64748b; }}
  .threshold {{ font-size:.75rem; margin-top:6px; }}
  .ok   {{ color:#4ade80; }}
  .warn {{ color:#f87171; }}
  canvas {{ max-height:180px; }}
</style>
</head>
<body>
<h1>📊 K4-L3B Day 13 — Monitoring &amp; LLMOps Dashboard</h1>
<div class="meta">Source: data/logs.jsonl &nbsp;|&nbsp; Time range: last 60 min &nbsp;|&nbsp; Refresh: 30s &nbsp;|&nbsp; Generated: {generated}</div>
<div class="grid">

  <!-- 1. LATENCY -->
  <div class="card">
    <h2>⏱ Latency &amp; TTFT (ms)</h2>
    <div class="kpi">
      <div class="kpi-item"><div class="kpi-val">{p50}</div><div class="kpi-lbl">P50 ms</div></div>
      <div class="kpi-item"><div class="kpi-val" style="color:{p95_color}">{p95}</div><div class="kpi-lbl">P95 ms</div></div>
      <div class="kpi-item"><div class="kpi-val">{p99}</div><div class="kpi-lbl">P99 ms</div></div>
      <div class="kpi-item"><div class="kpi-val">{tp95}</div><div class="kpi-lbl">TTFT P95</div></div>
    </div>
    <div class="threshold {p95_ok}">SLO: P95 ≤ 3000 ms — {p95_status}</div>
    <canvas id="latChart"></canvas>
  </div>

  <!-- 2. TRAFFIC -->
  <div class="card">
    <h2>📈 Traffic (req/min)</h2>
    <div class="kpi">
      <div class="kpi-item"><div class="kpi-val">{total_req}</div><div class="kpi-lbl">Total Requests</div></div>
    </div>
    <div class="threshold ok">SLO: rate ≥ 1 req/min</div>
    <canvas id="trafficChart"></canvas>
  </div>

  <!-- 3. ERRORS -->
  <div class="card">
    <h2>🚨 Errors &amp; Retrieval</h2>
    <div class="kpi">
      <div class="kpi-item"><div class="kpi-val" style="color:{err_color}">{error_rate}%</div><div class="kpi-lbl">Error Rate</div></div>
      <div class="kpi-item"><div class="kpi-val">{retrieval_success}%</div><div class="kpi-lbl">Retrieval Success</div></div>
      <div class="kpi-item"><div class="kpi-val">{total_fail}</div><div class="kpi-lbl">Failed</div></div>
    </div>
    <div class="threshold {err_ok}">SLO: Error rate ≤ 2% — {err_status}</div>
  </div>

  <!-- 4. COST -->
  <div class="card">
    <h2>💰 Cost (USD)</h2>
    <div class="kpi">
      <div class="kpi-item"><div class="kpi-val">${total_cost}</div><div class="kpi-lbl">Total</div></div>
    </div>
    <div class="threshold {cost_ok}">SLO: Total ≤ $2.50 — {cost_status}</div>
    <canvas id="costChart"></canvas>
  </div>

  <!-- 5. TOKENS -->
  <div class="card">
    <h2>🔤 Tokens</h2>
    <div class="kpi">
      <div class="kpi-item"><div class="kpi-val">{tokens_in}</div><div class="kpi-lbl">Input Tokens</div></div>
      <div class="kpi-item"><div class="kpi-val">{tokens_out}</div><div class="kpi-lbl">Output Tokens</div></div>
      <div class="kpi-item"><div class="kpi-val">{tokens_total}</div><div class="kpi-lbl">Total</div></div>
    </div>
    <div class="threshold ok">SLO: Total ≤ 50,000 tokens</div>
  </div>

  <!-- 6. QUALITY -->
  <div class="card">
    <h2>⭐ Quality Score</h2>
    <div class="kpi">
      <div class="kpi-item"><div class="kpi-val" style="color:{qual_color}">{mean_quality}</div><div class="kpi-lbl">Mean Score</div></div>
    </div>
    <div class="threshold {qual_ok}">SLO: Mean ≥ 0.75 — {qual_status}</div>
    <canvas id="qualChart"></canvas>
  </div>

</div>

<script>
const latLabels  = {lat_labels_js};
const latP95     = {lat_p95_js};
const reqLabels  = {req_labels_js};
const reqCounts  = {req_counts_js};
const costLabels = {cost_labels_js};
const costVals   = {cost_vals_js};
const qualScores = {qual_scores_js};

const cfg = (labels, datasets, yLabel) => ({{
  type:'line', data:{{labels, datasets}},
  options:{{responsive:true, plugins:{{legend:{{labels:{{color:'#94a3b8',boxWidth:10}}}}}},
    scales:{{x:{{ticks:{{color:'#64748b',maxRotation:0}},grid:{{color:'#1e293b'}}}},
             y:{{ticks:{{color:'#64748b'}},grid:{{color:'#334155'}},title:{{display:true,text:yLabel,color:'#64748b'}}}}}}}}
}});

new Chart('latChart', cfg(latLabels,[
  {{label:'P95 ms',data:latP95,borderColor:'#38bdf8',backgroundColor:'rgba(56,189,248,.15)',fill:true,tension:.3,pointRadius:3}}
],'ms'));

new Chart('trafficChart', cfg(reqLabels,[
  {{label:'req/min',data:reqCounts,borderColor:'#a78bfa',backgroundColor:'rgba(167,139,250,.15)',fill:true,tension:.3,pointRadius:3}}
],'requests'));

new Chart('costChart', cfg(costLabels,[
  {{label:'cost USD',data:costVals,borderColor:'#fbbf24',backgroundColor:'rgba(251,191,36,.15)',fill:true,tension:.3,pointRadius:3}}
],'USD'));

// quality histogram
const qualBuckets = [0,0,0,0,0];
qualScores.forEach(s => {{ const i=Math.min(4,Math.floor(s*5)); qualBuckets[i]++; }});
new Chart('qualChart', {{
  type:'bar',
  data:{{labels:['0-.2','.2-.4','.4-.6','.6-.8','.8-1'],datasets:[{{label:'count',data:qualBuckets,backgroundColor:'rgba(52,211,153,.6)'}}]}},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{
    x:{{ticks:{{color:'#64748b'}},grid:{{color:'#1e293b'}}}},
    y:{{ticks:{{color:'#64748b'}},grid:{{color:'#334155'}},title:{{display:true,text:'# traces',color:'#64748b'}}}}
  }}}}
}});
</script>
</body>
</html>
"""


def main() -> None:
    logs = load_logs(time_range_minutes=60)
    if not logs:
        print(f"[WARN] Không tìm thấy log tại {LOG_PATH}. Hãy chạy load_test.py trước.")

    m = compute(logs)

    def ok_warn(val, threshold, op):
        if op == "lte":
            return ("ok", "✅ OK") if val <= threshold else ("warn", "❌ BREACH")
        return ("ok", "✅ OK") if val >= threshold else ("warn", "❌ BREACH")

    p95_ok, p95_status   = ok_warn(m["p95"],            3000, "lte")
    err_ok, err_status   = ok_warn(m["error_rate"],     2.0,  "lte")
    cost_ok, cost_status = ok_warn(m["total_cost"],     2.5,  "lte")
    qual_ok, qual_status = ok_warn(m["mean_quality"],   0.75, "gte")

    html = HTML_TMPL.format(
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        p50=m["p50"], p95=m["p95"], p99=m["p99"], tp95=m["tp95"],
        p95_color="#f87171" if p95_ok == "warn" else "#38bdf8",
        p95_ok=p95_ok, p95_status=p95_status,
        total_req=m["total_req"],
        error_rate=m["error_rate"], total_fail=m["total_fail"],
        retrieval_success=m["retrieval_success"],
        err_color="#f87171" if err_ok == "warn" else "#4ade80",
        err_ok=err_ok, err_status=err_status,
        total_cost=m["total_cost"],
        cost_ok=cost_ok, cost_status=cost_status,
        tokens_in=m["tokens_in"], tokens_out=m["tokens_out"],
        tokens_total=m["tokens_in"] + m["tokens_out"],
        mean_quality=m["mean_quality"],
        qual_color="#f87171" if qual_ok == "warn" else "#4ade80",
        qual_ok=qual_ok, qual_status=qual_status,
        # JS arrays
        lat_labels_js=json.dumps(m["lat_labels"]),
        lat_p95_js=json.dumps(m["lat_p95_vals"]),
        req_labels_js=json.dumps(m["req_labels"]),
        req_counts_js=json.dumps(m["req_counts"]),
        cost_labels_js=json.dumps(m["cost_labels"]),
        cost_vals_js=json.dumps(m["cost_vals"]),
        qual_scores_js=json.dumps(m["quality_scores"]),
    )

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"✅ Dashboard generated: {OUT_PATH}")
    print(f"   Panels: Latency | Traffic | Errors | Cost | Tokens | Quality")
    print(f"   Logs loaded: {len(logs)} records")
    print(f"   P50={m['p50']}ms  P95={m['p95']}ms  P99={m['p99']}ms  TTFT_P95={m['tp95']}ms")
    print(f"   Requests={m['total_req']}  Errors={m['total_fail']}  ErrorRate={m['error_rate']}%")
    print(f"   Cost=${m['total_cost']}  Tokens={m['tokens_in']+m['tokens_out']}  Quality={m['mean_quality']}")

    webbrowser.open(OUT_PATH.as_uri())
    print(f"\nOpening in browser... (or open manually: {OUT_PATH})")


if __name__ == "__main__":
    main()
