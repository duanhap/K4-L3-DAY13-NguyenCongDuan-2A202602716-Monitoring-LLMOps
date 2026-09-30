from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = Path(os.getenv("LOG_PATH", str(ROOT / "data" / "logs.jsonl")))
CONFIG_PATH = ROOT / "config" / "dashboard.yaml"


def _config() -> dict[str, Any]:
    try:
        return (yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}).get("dashboard", {})
    except (OSError, yaml.YAMLError):
        return {}


def _percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * pct / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return round(values[lo] + (values[hi] - values[lo]) * (pos - lo), 2)


def _read_records(now: datetime, minutes: int) -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    records = []
    cutoff = now - timedelta(minutes=minutes)
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            item = json.loads(line)
            ts = datetime.fromisoformat(str(item.get("ts", "")).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts = ts.astimezone(timezone.utc)
            if ts >= cutoff:
                item["_ts"] = ts
                records.append(item)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return records


def _series(records: list[dict[str, Any]], now: datetime, minutes: int, event: str, field: str | None = None) -> list[dict[str, Any]]:
    first = now.replace(second=0, microsecond=0) - timedelta(minutes=minutes - 1)
    buckets = {first + timedelta(minutes=i): 0.0 for i in range(minutes)}
    for item in records:
        if item.get("event") != event:
            continue
        key = item["_ts"].replace(second=0, microsecond=0)
        if key in buckets:
            try:
                buckets[key] += float(item.get(field, 1) or 0) if field else 1
            except (TypeError, ValueError):
                pass
    return [{"time": k.isoformat(), "value": round(v, 6)} for k, v in buckets.items()]


def build_dashboard_data(minutes: int = 60) -> dict[str, Any]:
    minutes = max(1, min(int(minutes), 60))
    now = datetime.now(timezone.utc)
    records = _read_records(now, minutes)
    panels_cfg = {p.get("id"): p for p in _config().get("panels", [])}
    threshold = lambda key: panels_cfg.get(key, {}).get("threshold", {})
    requests = [r for r in records if r.get("event") == "request_received"]
    failures = [r for r in records if r.get("event") == "request_failed"]
    responses = [r for r in records if r.get("event") == "response_sent"]
    tool_results = [r for r in records if r.get("tool_success") is not None]
    latency = [float(r["latency_ms"]) for r in responses if r.get("latency_ms") is not None]
    ttft = [float(r["ttft_ms"]) for r in responses if r.get("ttft_ms") is not None]
    costs = [float(r["cost_usd"]) for r in responses if r.get("cost_usd") is not None]
    quality = [float(r["quality_score"]) for r in responses if r.get("quality_score") is not None]
    return {
        "generated_at": now.isoformat(), "time_range_minutes": minutes,
        "refresh_seconds": 30, "records_in_window": len(records), "empty": not records,
        "panels": {
            "latency": {"p50_ms": _percentile(latency, 50), "p95_ms": _percentile(latency, 95),
                        "p99_ms": _percentile(latency, 99), "ttft_p95_ms": _percentile(ttft, 95),
                        "threshold": threshold("latency")},
            "traffic": {"request_count": len(requests), "requests_per_minute": round(len(requests) / minutes, 2),
                        "series": _series(records, now, minutes, "request_received"), "threshold": threshold("traffic")},
            "errors": {"failed_requests": len(failures),
                       "error_rate_pct": round(100 * len(failures) / len(requests), 2) if requests else 0,
                       "retrieval_success_rate_pct": round(100 * sum(bool(r.get("tool_success")) for r in tool_results) / len(tool_results), 2) if tool_results else None,
                       "threshold": threshold("errors")},
            "cost": {"total_usd": round(sum(costs), 6),
                     "series": _series(records, now, minutes, "response_sent", "cost_usd"), "threshold": threshold("cost")},
            "tokens": {"input_total": sum(int(r.get("tokens_in", 0) or 0) for r in responses),
                       "output_total": sum(int(r.get("tokens_out", 0) or 0) for r in responses), "threshold": threshold("tokens")},
            "quality": {"mean": round(mean(quality), 4) if quality else None, "threshold": threshold("quality")},
        },
    }


DASHBOARD_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Day 13 Monitoring Dashboard</title><style>
:root{color-scheme:dark;--bg:#0b1020;--card:#141e32;--line:#2a3955;--muted:#9aabc5;--text:#edf3ff;--cyan:#59d7d1;--amber:#f2c66d}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 420px at 85% -10%,#1e3152,transparent 65%),var(--bg);color:var(--text);font:14px/1.45 Segoe UI,Arial,sans-serif}.wrap{max-width:1440px;margin:auto;padding:30px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}.eyebrow{color:var(--cyan);letter-spacing:.17em;text-transform:uppercase;font-size:11px}.title{font-size:28px;font-weight:700;margin:5px 0}.muted{color:var(--muted)}select{background:#111a2c;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{background:linear-gradient(145deg,#17233a,#111a2c);border:1px solid var(--line);border-radius:15px;padding:19px;min-height:238px}.card h2{font-size:15px;margin:0 0 3px}.unit{color:var(--muted);font-size:10px;letter-spacing:.12em;text-transform:uppercase}.metrics{display:flex;gap:18px;flex-wrap:wrap;margin:22px 0 16px}.metric strong{display:block;font-size:24px}.metric span{font-size:11px;color:var(--muted)}.pill{float:right;color:#c1d4f3;border:1px solid #344765;border-radius:20px;padding:3px 8px;font-size:10px}.chart{width:100%;height:90px;margin-top:10px}.chart line{stroke:#33425c}.chart polyline{fill:none;stroke:var(--cyan);stroke-width:2.5}.chart rect{fill:#59d7d177}.chart text{fill:var(--muted);font-size:10px}.foot{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:18px}.warning{color:var(--amber)}@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.wrap{padding:18px}.grid{grid-template-columns:1fr}.top{align-items:flex-start;gap:15px;flex-direction:column}}
</style></head><body><main class="wrap"><header class="top"><div><div class="eyebrow">Observability · LLMOps</div><div class="title">Day 13 Monitoring Dashboard</div><div class="muted">Live view from sanitized application logs</div></div><label>Time range&nbsp; <select id="range"><option value="60" selected>Past 60 minutes</option><option value="30">Past 30 minutes</option><option value="15">Past 15 minutes</option></select>&nbsp; <span class="muted">Refresh 30s</span></label></header><section id="grid" class="grid"></section><footer class="foot"><span id="status">Loading…</span><span>Thresholds: config/dashboard.yaml</span></footer></main><script>
const labels={latency:['Latency percentiles and TTFT','ms'],traffic:['Request traffic','requests/minute'],errors:['Error rate and retrieval success','percent'],cost:['Cost over time','USD'],tokens:['Input and output tokens','tokens'],quality:['Quality proxy','score 0–1']};const f=(x,d=1)=>x===null||x===undefined?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d});
function chart(s,bars=false){if(!s?.length)return '';const v=s.map(x=>+x.value),max=Math.max(...v,1),min=Math.min(...v,0),step=276/Math.max(v.length-1,1);if(bars)return `<svg class="chart" viewBox="0 0 300 92" preserveAspectRatio="none"><line x1="8" y1="77" x2="292" y2="77"/>${v.map((n,i)=>{let h=n/max*62;return `<rect x="${10+i*280/v.length}" y="${77-h}" width="${Math.max(1,280/v.length-2)}" height="${h}" rx="2"/>`}).join('')}</svg>`;const span=max-min||1;return `<svg class="chart" viewBox="0 0 300 92" preserveAspectRatio="none"><line x1="8" y1="77" x2="292" y2="77"/><polyline points="${v.map((n,i)=>`${12+i*step},${76-(n-min)/span*60}`).join(' ')}"/></svg>`}
function card(id,p){let body='';if(id==='latency')body=`<div class="metrics">${[['P50',p.p50_ms],['P95',p.p95_ms],['P99',p.p99_ms],['TTFT P95',p.ttft_p95_ms]].map(([k,v])=>`<div class="metric"><strong>${f(v)}</strong><span>${k}</span></div>`).join('')}</div><div class="muted">P95 threshold ≤ ${f(p.threshold.value)} ms</div>`;if(id==='traffic')body=`<div class="metrics"><div class="metric"><strong>${f(p.request_count,0)}</strong><span>requests</span></div><div class="metric"><strong>${f(p.requests_per_minute,2)}</strong><span>requests/min</span></div></div>${chart(p.series,true)}`;if(id==='errors')body=`<div class="metrics"><div class="metric"><strong>${f(p.error_rate_pct,2)}%</strong><span>error rate · ${f(p.failed_requests,0)} failed</span></div><div class="metric"><strong>${f(p.retrieval_success_rate_pct)}%</strong><span>retrieval success</span></div></div><div class="muted">Error threshold ≤ ${f(p.threshold.value)}%</div>`;if(id==='cost')body=`<div class="metrics"><div class="metric"><strong>$${f(p.total_usd,4)}</strong><span>total cost</span></div></div>${chart(p.series)}`;if(id==='tokens')body=`<div class="metrics"><div class="metric"><strong>${f(p.input_total,0)}</strong><span>input tokens</span></div><div class="metric"><strong>${f(p.output_total,0)}</strong><span>output tokens</span></div></div><div class="muted">Total threshold ≤ ${f(p.threshold.value,0)} tokens</div>`;if(id==='quality')body=`<div class="metrics"><div class="metric"><strong>${f(p.mean,3)}</strong><span>mean score</span></div></div><div class="muted">Quality threshold ≥ ${f(p.threshold.value,2)}</div>`;return `<article class="card"><span class="pill">${id.toUpperCase()}</span><h2>${labels[id][0]}</h2><div class="unit">${labels[id][1]}</div>${body}</article>`}
async function refresh(){try{let r=await fetch('/dashboard/data?minutes='+document.querySelector('#range').value,{cache:'no-store'});let d=await r.json();document.querySelector('#grid').innerHTML=Object.keys(labels).map(k=>card(k,d.panels[k])).join('');document.querySelector('#status').textContent=d.empty?'No records in this window. Run a workload to populate the dashboard.':`${d.records_in_window} log records · updated ${new Date(d.generated_at).toLocaleTimeString()}`}catch(e){document.querySelector('#status').textContent='Dashboard data unavailable: '+e.message}}document.querySelector('#range').addEventListener('change',refresh);refresh();setInterval(refresh,30000);
</script></body></html>'''
