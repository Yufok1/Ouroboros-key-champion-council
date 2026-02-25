#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = os.environ.get("CC_BASE_URL", "http://127.0.0.1:7866")
PROGRESS_FILE = Path('data/tool_audit_progress.json')


def jget(path, timeout=20):
    req = urllib.request.Request(BASE + path, method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode('utf-8', errors='replace'))


def jpost(path, payload, headers=None, timeout=10):
    body = json.dumps(payload).encode('utf-8')
    h = {'Content-Type': 'application/json'}
    if headers:
        h.update(headers)
    req = urllib.request.Request(BASE + path, data=body, headers=h, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode('utf-8', errors='replace')
            try:
                return r.status, json.loads(txt) if txt else {}
            except Exception:
                return r.status, {'_raw': txt}
    except urllib.error.HTTPError as e:
        txt = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, json.loads(txt) if txt else {}
        except Exception:
            return e.code, {'_raw': txt}
    except Exception as e:
        return 0, {'error': str(e)}


def from_schema(schema):
    if not isinstance(schema, dict):
        return {}
    t = schema.get('type')
    if t == 'string':
        return 'smoke'
    if t == 'integer':
        return 1
    if t == 'number':
        return 1
    if t == 'boolean':
        return True
    if t == 'array':
        return []
    if t == 'object':
        out = {}
        for k in schema.get('required', []):
            p = (schema.get('properties') or {}).get(k, {})
            out[k] = from_schema(p)
        return out
    for key in ('anyOf', 'oneOf'):
        opts = schema.get(key)
        if isinstance(opts, list):
            for opt in opts:
                if isinstance(opt, dict) and opt.get('type') != 'null':
                    return from_schema(opt)
    return {}


def build_args(name, schema):
    props = (schema or {}).get('properties', {}) if isinstance(schema, dict) else {}
    required = (schema or {}).get('required', []) if isinstance(schema, dict) else []
    args = {}
    for k in required:
        if k in props:
            args[k] = from_schema(props[k])
    for k, p in props.items():
        if k not in args and isinstance(p, dict) and p.get('default') is not None:
            args[k] = p.get('default')

    # pragmatic overrides
    if name == 'chat':
        args['message'] = 'ping'
    if name == 'deliberate':
        args['question'] = 'status?'
    if name == 'imagine':
        args['scenario'] = 'smoke scenario'; args['steps'] = 1
    if name in ('forward', 'infer', 'embed_text', 'generate', 'classify', 'rerank'):
        args['text'] = args.get('text', 'smoke')
        args['query'] = args.get('query', 'smoke')
    if name == 'batch_forward':
        args['inputs'] = ['smoke']
    if name == 'batch_embed':
        args['texts'] = ['smoke']
    if name == 'pipe':
        args['input_text'] = 'smoke'; args['pipeline'] = [0]
    if name == 'compare':
        args['input_text'] = 'smoke'
    if name == 'invoke_slot':
        args['slot'] = 0; args['text'] = 'smoke'; args['mode'] = 'auto'
    if name in ('bag_get', 'bag_forget', 'materialize', 'pocket', 'summon'):
        args['key'] = 'smoke_key'
    if name == 'bag_put':
        args['key'] = 'smoke_key'; args['value'] = 'smoke_value'
    if name == 'bag_search':
        args['query'] = 'smoke'
    if name == 'workflow_create':
        args['definition'] = json.dumps({'name':'smoke_workflow','nodes':[{'id':'n1','type':'tool','data':{'tool':'heartbeat','args':{}}}],'edges':[]})
    if name == 'workflow_update':
        args['workflow_id'] = 'smoke_workflow'; args['definition'] = json.dumps({'name':'smoke_workflow','nodes':[],'edges':[]})
    if name in ('workflow_execute','workflow_get','workflow_delete','workflow_history'):
        args['workflow_id'] = 'smoke_workflow'
    if name == 'workflow_status':
        args['execution_id'] = 'smoke_execution'
    if name == 'workflow_history' and 'limit' in props:
        args['limit'] = '5'
    if name == 'hold_resolve':
        args['hold_id'] = 'smoke_hold'; args['action'] = 'accept'
    if name.startswith('hub_search'):
        args['query'] = 'tiny model'; args['limit'] = 3
    if name == 'hub_info':
        args['model_id'] = 'distilbert-base-uncased'
    if name == 'hub_download':
        args['model_id'] = 'distilbert-base-uncased'
    if name == 'hub_tasks':
        args['task'] = 'text-classification'
    if name in ('plug_model','hub_plug'):
        args['model_id'] = 'distilbert-base-uncased'
    if name.startswith('vast_'):
        if 'instance_id' in props:
            args['instance_id'] = 0
        if name == 'vast_search':
            args['query'] = 'gpu'; args['limit'] = 3
        if name == 'vast_details':
            args['offer_id'] = 0
        if name == 'vast_rent':
            args['offer_id'] = 0
    return args


def load_progress():
    if not PROGRESS_FILE.exists():
        return {'started_ms': int(time.time()*1000), 'tools_total': 0, 'calls': []}
    try:
        return json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {'started_ms': int(time.time()*1000), 'tools_total': 0, 'calls': []}


def save_progress(data):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')


def summarize(data):
    calls = data.get('calls', [])
    total = len(calls)
    ok = sum(1 for c in calls if c.get('http_status') == 200 and not c.get('top_error'))
    app_err = sum(1 for c in calls if c.get('isError') or c.get('top_error'))
    transport = sum(1 for c in calls if c.get('http_status') in (0, 502, 503, 504))
    return {
        'recorded_calls': total,
        'ok_http200_no_top_error': ok,
        'app_error_or_isError': app_err,
        'transport_or_timeout': transport,
    }


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 25

    _, tools_payload = jget('/api/tools', timeout=30)
    tools = tools_payload.get('result', {}).get('tools', []) if isinstance(tools_payload, dict) else []

    batch = tools[start:start+size]
    prog = load_progress()
    prog['tools_total'] = len(tools)

    existing = {(c.get('tool'), c.get('index')) for c in prog.get('calls', [])}

    for idx, t in enumerate(batch, start=start):
        name = t.get('name')
        if (name, idx) in existing:
            continue
        args = build_args(name, t.get('inputSchema') or {})
        code, payload = jpost(f'/api/tool/{name}', args, headers={'X-Source': 'external'}, timeout=10)
        result = payload.get('result') if isinstance(payload, dict) else None
        top_error = payload.get('error') if isinstance(payload, dict) else None
        is_error = bool(result.get('isError')) if isinstance(result, dict) else False
        prog['calls'].append({
            'index': idx,
            'tool': name,
            'args': args,
            'http_status': code,
            'top_error': top_error,
            'isError': is_error,
            'has_result': isinstance(result, dict),
        })

    save_progress(prog)

    # activity coverage for completed calls
    _, activity = jget('/api/activity-log?limit=5000', timeout=30)
    entries = activity.get('entries', []) if isinstance(activity, dict) else []
    started_ms = int(prog.get('started_ms', 0))
    run_ext = [e for e in entries if isinstance(e, dict) and e.get('source') == 'external' and e.get('timestamp', 0) >= started_ms]
    seen = {e.get('tool') for e in run_ext if e.get('tool')}
    called_tools = {c.get('tool') for c in prog.get('calls', []) if c.get('tool')}
    missing = sorted(t for t in called_tools if t not in seen)

    out = {
        'batch_start': start,
        'batch_size': size,
        'batch_end_exclusive': start + len(batch),
        'tools_total': len(tools),
        'summary': summarize(prog),
        'activity': {
            'external_entries_since_start': len(run_ext),
            'unique_external_tools_seen': len(seen),
            'called_tools_total': len(called_tools),
            'missing_registration_count': len(missing),
            'missing_registration_sample': missing[:20],
        },
        'progress_file': str(PROGRESS_FILE),
    }
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
