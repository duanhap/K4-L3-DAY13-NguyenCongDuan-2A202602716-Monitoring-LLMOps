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


def _challenge_context() -> dict[str, Any]:
    """Read only dashboard filter settings; never return the challenge payload."""
    try:
        payload = json.loads((ROOT / "config" / "challenge.json").read_text(encoding="utf-8"))
        feature = payload.get("affected_feature")
        threshold = payload.get("latency_threshold_ms")
        if isinstance(feature, str) and feature and isinstance(threshold, int) and threshold > 0:
            return {"feature": feature, "latency_threshold_ms": threshold}
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
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


def _event_series(records: list[dict[str, Any]], event: str, field: str) -> list[dict[str, Any]]:
    """Return one timestamped sample per event for incident timelines."""
    points = []
    for item in records:
        if item.get("event") != event or item.get(field) is None:
            continue
        try:
            points.append({"time": item["_ts"].isoformat(), "value": float(item[field])})
        except (TypeError, ValueError, KeyError):
            continue
    return points


def build_dashboard_data(minutes: int = 60, scope: str = "all") -> dict[str, Any]:
    minutes = max(1, min(int(minutes), 60))
    scope = "challenge" if scope == "challenge" else "all"
    now = datetime.now(timezone.utc)
    records = _read_records(now, minutes)
    challenge = _challenge_context() if scope == "challenge" else {}
    if scope == "challenge":
        records = [r for r in records if challenge and r.get("feature") == challenge["feature"]]
    panels_cfg = {p.get("id"): p for p in _config().get("panels", [])}
    threshold = lambda key: panels_cfg.get(key, {}).get("threshold", {})
    latency_threshold = threshold("latency")
    if challenge:
        latency_threshold = {
            "aggregation": "p95", "operator": "lte",
            "value": challenge["latency_threshold_ms"], "source": "challenge",
        }
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
        "scope": scope,
        "scope_feature": challenge.get("feature") if challenge else None,
        "challenge_filter_available": bool(_challenge_context()),
        "refresh_seconds": 30, "records_in_window": len(records), "empty": not records,
        "panels": {
            "latency": {"p50_ms": _percentile(latency, 50), "p95_ms": _percentile(latency, 95),
                        "p99_ms": _percentile(latency, 99), "ttft_p95_ms": _percentile(ttft, 95),
                        "series": _event_series(records, "response_sent", "latency_ms"),
                        "ttft_series": _event_series(records, "response_sent", "ttft_ms"),
                        "threshold": latency_threshold},
            "traffic": {"request_count": len(requests), "requests_per_minute": round(len(requests) / minutes, 2),
                        "series": _series(records, now, minutes, "request_received"), "threshold": threshold("traffic")},
            "errors": {"failed_requests": len(failures),
                       "error_rate_pct": round(100 * len(failures) / len(requests), 2) if requests else 0,
                       "retrieval_success_rate_pct": round(100 * sum(bool(r.get("tool_success")) for r in tool_results) / len(tool_results), 2) if tool_results else None,
                       "series": [
                           {"label": "Error rate", "value": round(100 * len(failures) / len(requests), 2) if requests else 0},
                           {"label": "Retrieval success", "value": round(100 * sum(bool(r.get("tool_success")) for r in tool_results) / len(tool_results), 2) if tool_results else 0},
                       ],
                       "threshold": threshold("errors")},
            "cost": {"total_usd": round(sum(costs), 6),
                     "series": _series(records, now, minutes, "response_sent", "cost_usd"), "threshold": threshold("cost")},
            "tokens": {"input_total": sum(int(r.get("tokens_in", 0) or 0) for r in responses),
                       "output_total": sum(int(r.get("tokens_out", 0) or 0) for r in responses),
                       "input_series": _event_series(records, "response_sent", "tokens_in"),
                       "output_series": _event_series(records, "response_sent", "tokens_out"),
                       "threshold": threshold("tokens")},
            "quality": {"mean": round(mean(quality), 4) if quality else None,
                        "series": _event_series(records, "response_sent", "quality_score"), "threshold": threshold("quality")},
        },
    }


DASHBOARD_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>.wrap{max-width:1920px!important}.top{border-bottom:1px solid var(--line);padding-bottom:18px}.card{min-height:400px!important;background:#1b293e!important;border-color:#293c58!important;display:flex!important;flex-direction:column}.chart{height:175px!important;margin-top:auto!important;overflow:visible}.chart .gridline{stroke:#34445d;stroke-width:1}.chart .axis{stroke:#60728d;stroke-width:1}.chart .line-a{fill:none;stroke:#35bdf3;stroke-width:2.5}.chart .line-b{fill:none;stroke:#ffc857;stroke-width:2;stroke-dasharray:5 4}.chart .threshold{stroke:#ff7272;stroke-width:2;stroke-dasharray:6 4}.chart .bar-a{fill:#35bdf3}.chart .bar-b{fill:#a65cf1}.chart .dot-a{fill:#35bdf3}.chart text{fill:var(--muted);font-size:9px}.metric strong{color:#35bdf3}.legend{font-size:11px;color:var(--muted);display:flex;gap:14px;margin-top:7px}.legend i{display:inline-block;width:13px;height:3px;vertical-align:middle;margin-right:4px;background:#35bdf3}.threshold-note{color:#35bdf3;background:#203c54;border-radius:4px;padding:4px 8px;font-size:11px;margin-top:8px}.status-breach{color:#ff7272;font-weight:700}</style>
<title>Day 13 Monitoring Dashboard</title><style>
:root{color-scheme:dark;--bg:#0b1020;--card:#141e32;--line:#2a3955;--muted:#9aabc5;--text:#edf3ff;--cyan:#59d7d1;--amber:#f2c66d}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 420px at 85% -10%,#1e3152,transparent 65%),var(--bg);color:var(--text);font:14px/1.45 Segoe UI,Arial,sans-serif}.wrap{max-width:1440px;margin:auto;padding:30px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}.eyebrow{color:var(--cyan);letter-spacing:.17em;text-transform:uppercase;font-size:11px}.title{font-size:28px;font-weight:700;margin:5px 0}.muted{color:var(--muted)}select{background:#111a2c;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.card{background:linear-gradient(145deg,#17233a,#111a2c);border:1px solid var(--line);border-radius:15px;padding:19px;min-height:238px}.card h2{font-size:15px;margin:0 0 3px}.unit{color:var(--muted);font-size:10px;letter-spacing:.12em;text-transform:uppercase}.metrics{display:flex;gap:18px;flex-wrap:wrap;margin:22px 0 16px}.metric strong{display:block;font-size:24px}.metric span{font-size:11px;color:var(--muted)}.pill{float:right;color:#c1d4f3;border:1px solid #344765;border-radius:20px;padding:3px 8px;font-size:10px}.chart{width:100%;height:90px;margin-top:10px}.chart line{stroke:#33425c}.chart polyline{fill:none;stroke:var(--cyan);stroke-width:2.5}.chart rect{fill:#59d7d177}.chart text{fill:var(--muted);font-size:10px}.foot{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:18px}.warning{color:var(--amber)}@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:600px){.wrap{padding:18px}.grid{grid-template-columns:1fr}.top{align-items:flex-start;gap:15px;flex-direction:column}}
</style></head><body><main class="wrap"><header class="top"><div><div class="eyebrow">Observability · LLMOps</div><div class="title">Day 13 Monitoring Dashboard</div><div class="muted">Live view from sanitized application logs</div></div><label>Scope&nbsp;<select id="scope"><option value="all">All features</option><option value="challenge">Challenge feature</option></select>&nbsp; Time range&nbsp; <select id="range"><option value="60" selected>Past 60 minutes</option><option value="30">Past 30 minutes</option><option value="15">Past 15 minutes</option></select>&nbsp; <span class="muted">Refresh 30s</span></label></header><section id="grid" class="grid"></section><footer class="foot"><span id="status">Loading…</span><span>Thresholds: config/dashboard.yaml</span></footer></main><script>
const labels={latency:['Latency percentiles and TTFT','ms'],traffic:['Request traffic','requests/minute'],errors:['Error rate and retrieval success','percent'],cost:['Cost over time','USD'],tokens:['Input and output tokens','tokens'],quality:['Quality proxy','score 0–1']};const f=(x,d=1)=>x===null||x===undefined?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d});
function chart(s,bars=false){if(!s?.length)return '';const v=s.map(x=>+x.value),max=Math.max(...v,1),min=Math.min(...v,0),step=276/Math.max(v.length-1,1);if(bars)return `<svg class="chart" viewBox="0 0 300 92" preserveAspectRatio="none"><line x1="8" y1="77" x2="292" y2="77"/>${v.map((n,i)=>{let h=n/max*62;return `<rect x="${10+i*280/v.length}" y="${77-h}" width="${Math.max(1,280/v.length-2)}" height="${h}" rx="2"/>`}).join('')}</svg>`;const span=max-min||1;return `<svg class="chart" viewBox="0 0 300 92" preserveAspectRatio="none"><line x1="8" y1="77" x2="292" y2="77"/><polyline points="${v.map((n,i)=>`${12+i*step},${76-(n-min)/span*60}`).join(' ')}"/></svg>`}
function card(id,p){let body='';if(id==='latency')body=`<div class="metrics">${[['P50',p.p50_ms],['P95',p.p95_ms],['P99',p.p99_ms],['TTFT P95',p.ttft_p95_ms]].map(([k,v])=>`<div class="metric"><strong>${f(v)}</strong><span>${k}</span></div>`).join('')}</div><div class="muted">P95 threshold ≤ ${f(p.threshold.value)} ms${p.threshold.source==='challenge'?' · challenge threshold':''} · ${Number(p.p95_ms||0)>Number(p.threshold.value)?'BREACH':'within threshold'}</div>`;if(id==='traffic')body=`<div class="metrics"><div class="metric"><strong>${f(p.request_count,0)}</strong><span>requests</span></div><div class="metric"><strong>${f(p.requests_per_minute,2)}</strong><span>requests/min</span></div></div>${chart(p.series,true)}`;if(id==='errors')body=`<div class="metrics"><div class="metric"><strong>${f(p.error_rate_pct,2)}%</strong><span>error rate · ${f(p.failed_requests,0)} failed</span></div><div class="metric"><strong>${f(p.retrieval_success_rate_pct)}%</strong><span>retrieval success</span></div></div><div class="muted">Error threshold ≤ ${f(p.threshold.value)}%</div>`;if(id==='cost')body=`<div class="metrics"><div class="metric"><strong>$${f(p.total_usd,4)}</strong><span>total cost</span></div></div>${chart(p.series)}`;if(id==='tokens')body=`<div class="metrics"><div class="metric"><strong>${f(p.input_total,0)}</strong><span>input tokens</span></div><div class="metric"><strong>${f(p.output_total,0)}</strong><span>output tokens</span></div></div><div class="muted">Total threshold ≤ ${f(p.threshold.value,0)} tokens</div>`;if(id==='quality')body=`<div class="metrics"><div class="metric"><strong>${f(p.mean,3)}</strong><span>mean score</span></div></div><div class="muted">Quality threshold ≥ ${f(p.threshold.value,2)}</div>`;return `<article class="card"><span class="pill">${id.toUpperCase()}</span><h2>${labels[id][0]}</h2><div class="unit">${labels[id][1]}</div>${body}</article>`}
async function refresh(){try{let scope=document.querySelector('#scope').value;let r=await fetch('/dashboard/data?minutes='+document.querySelector('#range').value+'&scope='+scope,{cache:'no-store'});let d=await r.json();document.querySelector('#grid').innerHTML=Object.keys(labels).map(k=>card(k,d.panels[k])).join('');document.querySelector('#status').textContent=d.empty?'No records in this window. Run a workload to populate the dashboard.':`${d.records_in_window} log records · ${d.scope==='challenge'?'challenge feature: '+(d.scope_feature||'unavailable'):'all features'} · updated ${new Date(d.generated_at).toLocaleTimeString()}`}catch(e){document.querySelector('#status').textContent='Dashboard data unavailable: '+e.message}}document.querySelector('#range').addEventListener('change',refresh);document.querySelector('#scope').addEventListener('change',refresh);refresh();setInterval(refresh,30000);
</script><script>
function lineChart(series,threshold=null,second=null){const all=[...(series||[]),...(second||[])].map(x=>+x.value);if(threshold!==null)all.push(+threshold);if(!all.length)return '<div class="muted">No samples in this window</div>';const lo=Math.min(0,...all),hi=Math.max(...all,1),span=hi-lo||1,X=i=>42+i*540/Math.max(series.length-1,1),Y=v=>142-(v-lo)/span*118;const grid=[0,1,2,3].map(i=>{const y=20+i*39;return `<line class="gridline" x1="42" y1="${y}" x2="590" y2="${y}"/><text x="3" y="${y+3}">${f(hi-(hi-lo)*i/3,0)}</text>`}).join(''),a=series.map((p,i)=>`${X(i)},${Y(+p.value)}`).join(' '),b=second?second.map((p,i)=>`${X(i)},${Y(+p.value)}`).join(' '):'',th=threshold===null?'':`<line class="threshold" x1="42" y1="${Y(+threshold)}" x2="590" y2="${Y(+threshold)}"/>`;return `<svg class="chart" viewBox="0 0 600 170" preserveAspectRatio="none">${grid}<line class="axis" x1="42" y1="142" x2="590" y2="142"/>${th}<polyline class="line-a" points="${a}"/>${b?`<polyline class="line-b" points="${b}"/>`:''}${series.map((p,i)=>`<circle class="dot-a" cx="${X(i)}" cy="${Y(+p.value)}" r="2.7"><title>${new Date(p.time).toLocaleTimeString()} · ${f(p.value,1)}</title></circle>`).join('')}<text x="42" y="160">${new Date(series[0].time).toLocaleTimeString()}</text><text x="535" y="160">${new Date(series.at(-1).time).toLocaleTimeString()}</text></svg>`}
function barChart(series,second=null){if(!series?.length)return '<div class="muted">No samples in this window</div>';const max=Math.max(1,...series.map(x=>+x.value),...(second||[]).map(x=>+x.value)),slot=540/series.length,w=second?Math.min(13,slot/2-2):Math.min(25,slot-3),rects=series.map((p,i)=>{const x=45+i*slot+(second?0:slot/2-w/2),h=118*(+p.value)/max,h2=second?118*(+(second[i]?.value||0))/max:0;return `<rect class="bar-a" x="${x}" y="${142-h}" width="${w}" height="${h}" rx="1"/>${second?`<rect class="bar-b" x="${x+w+2}" y="${142-h2}" width="${w}" height="${h2}" rx="1"/>`:''}`}).join('');return `<svg class="chart" viewBox="0 0 600 170" preserveAspectRatio="none"><line class="gridline" x1="42" y1="24" x2="590" y2="24"/><line class="gridline" x1="42" y1="83" x2="590" y2="83"/><line class="axis" x1="42" y1="142" x2="590" y2="142"/><text x="3" y="27">${f(max,0)}</text><text x="3" y="86">${f(max/2,0)}</text>${rects}<text x="42" y="160">${series[0].time?new Date(series[0].time).toLocaleTimeString():series[0].label}</text><text x="535" y="160">${series.at(-1).time?new Date(series.at(-1).time).toLocaleTimeString():series.at(-1).label}</text></svg>`}
function card(id,p){let body='',plot='';if(id==='latency'){body=`<div class="metrics">${[['P50',p.p50_ms],['P95',p.p95_ms],['P99',p.p99_ms],['TTFT P95',p.ttft_p95_ms]].map(([k,v])=>`<div class="metric"><strong>${f(v)}</strong><span>${k}</span></div>`).join('')}</div>`;plot=lineChart(p.series,p.threshold.value,p.ttft_series);body+=`<div class="legend"><span><i></i>Latency ms</span><span><i style="background:#ffc857"></i>TTFT ms</span><span><i style="background:#ff7272"></i>Threshold ${f(p.threshold.value,0)} ms</span></div><div class="threshold-note">Threshold: P95 ≤ ${f(p.threshold.value,0)} ms${p.threshold.source==='challenge'?' · challenge':''} · <span class="${Number(p.p95_ms||0)>Number(p.threshold.value)?'status-breach':''}">${Number(p.p95_ms||0)>Number(p.threshold.value)?'BREACH':'within threshold'}</span></div>`}else if(id==='traffic'){body=`<div class="metrics"><div class="metric"><strong>${f(p.request_count,0)}</strong><span>TOTAL REQUESTS</span></div><div class="metric"><strong>${f(p.requests_per_minute,2)}</strong><span>RATE / MIN</span></div></div>`;plot=barChart(p.series)}else if(id==='errors'){body=`<div class="metrics"><div class="metric"><strong>${f(p.error_rate_pct,1)}%</strong><span>ERROR RATE · ${f(p.failed_requests,0)} failed</span></div><div class="metric"><strong>${f(p.retrieval_success_rate_pct,1)}%</strong><span>RETRIEVAL SUCCESS</span></div></div>`;plot=barChart([{label:'Error rate',value:p.error_rate_pct},{label:'Retrieval success',value:p.retrieval_success_rate_pct||0}]);body+=`<div class="threshold-note">Threshold: Error Rate ≤ ${f(p.threshold.value,1)}% · Retrieval ≥ 90%</div>`}else if(id==='cost'){body=`<div class="metrics"><div class="metric"><strong>$${f(p.total_usd,4)}</strong><span>TOTAL COST</span></div></div>`;plot=lineChart(p.series);body+=`<div class="threshold-note">Threshold: Total &lt; $${f(p.threshold.value,2)}</div>`}else if(id==='tokens'){body=`<div class="metrics"><div class="metric"><strong>${f(p.input_total,0)}</strong><span>TOKENS IN</span></div><div class="metric"><strong>${f(p.output_total,0)}</strong><span>TOKENS OUT</span></div><div class="metric"><strong>${f(p.input_total+p.output_total,0)}</strong><span>TOTAL TOKENS</span></div></div>`;plot=barChart(p.input_series,p.output_series);body+=`<div class="legend"><span><i></i>Tokens in</span><span><i style="background:#a65cf1"></i>Tokens out</span></div><div class="threshold-note">Threshold: Total &lt; ${f(p.threshold.value,0)} tokens</div>`}else{body=`<div class="metrics"><div class="metric"><strong>${f(p.mean,2)}</strong><span>MEAN QUALITY</span></div></div>`;plot=lineChart(p.series,p.threshold.value);body+=`<div class="legend"><span><i style="background:#ffc857"></i>Quality score</span><span><i style="background:#ff7272"></i>Threshold ${f(p.threshold.value,2)}</span></div><div class="threshold-note">Threshold: Mean ≥ ${f(p.threshold.value,2)}</div>`}return `<article class="card"><span class="pill">${id.toUpperCase()}</span><h2>${labels[id][0]}</h2><div class="unit">${labels[id][1]}</div>${body}${plot}</article>`}
</script><script>
function lineChart(series,threshold,second){threshold=threshold??null;const main=(series||[]).map(x=>+x.value);if(!main.length)return '<div class="muted">No samples in this window</div>';const mainScale=threshold===null?[...main]:[...main,+threshold],lo=Math.min(0,...mainScale),hi=Math.max(...mainScale,Number.EPSILON),span=hi-lo||1,X=i=>42+i*540/Math.max(main.length-1,1),Y=v=>142-(v-lo)/span*118,digits=hi<0.01?6:hi<1?4:hi<100?1:0;const grid=[0,1,2,3].map(i=>{const y=20+i*39;return '<line class="gridline" x1="42" y1="'+y+'" x2="590" y2="'+y+'"/><text x="3" y="'+(y+3)+'">'+f(hi-(hi-lo)*i/3,digits)+'</text>'}).join(''),points=series.map((p,i)=>X(i)+','+Y(+p.value)).join(' '),thresholdLine=threshold===null?'':'<line class="threshold" x1="42" y1="'+Y(+threshold)+'" x2="590" y2="'+Y(+threshold)+'"/>';let secondLine='';if(second&&second.length){const vals=second.map(x=>+x.value),max2=Math.max(...vals,Number.EPSILON),Y2=v=>142-(v/max2)*118;secondLine='<polyline class="line-b" points="'+second.map((p,i)=>X(i)+','+Y2(+p.value)).join(' ')+'"/>';}return '<svg class="chart" viewBox="0 0 600 170" preserveAspectRatio="none">'+grid+'<line class="axis" x1="42" y1="142" x2="590" y2="142"/>'+thresholdLine+'<polyline class="line-a" points="'+points+'"/>'+secondLine+series.map((p,i)=>'<circle class="dot-a" cx="'+X(i)+'" cy="'+Y(+p.value)+'" r="2.7"><title>'+new Date(p.time).toLocaleTimeString()+' · '+f(p.value,1)+'</title></circle>').join('')+'<text x="42" y="160">'+new Date(series[0].time).toLocaleTimeString()+'</text><text x="535" y="160">'+new Date(series[series.length-1].time).toLocaleTimeString()+'</text></svg>'}
</script></body></html>'''
