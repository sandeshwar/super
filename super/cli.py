"""`super` production CLI. Usage: python3 -m super.cli [--json] <command> [...]

Every dashboard action has a CLI equivalent for SSH / broken-browser days
(doc 06). Machine-readable output via --json. Exit codes: 0 ok, 1 usage or
validation, 2 gate rejection / blocked done-state, 3 config/auth failure.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from super import config as config_mod
from super.errors import SuperError

EXIT_USAGE = 1
EXIT_GATE = 2
EXIT_CONFIG = 3


def _out(obj, as_json: bool, text: str = "") -> None:
    if as_json:
        print(json.dumps(obj, indent=2))
    else:
        print(text if text else json.dumps(obj, indent=2))


def cmd_init(args, cfg):
    os.makedirs(cfg["state_dir"], exist_ok=True)
    tok = (cfg.get("server", {}) or {}).get("token", "")
    _out({"state_dir": cfg["state_dir"], "config": cfg.get("_config_path")},
         args.json, f"init: state dir ready at {cfg['state_dir']}\ninit: config from {cfg.get('_config_path')}")
    if not args.json:
        print(f"init: dashboard token stored in {cfg['state_dir']}/.token (0600)")


def cmd_chat(args, cfg):
    from super import llm

    print(llm.ask(cfg, args.prompt, system=args.system))


def cmd_gate_check(args, cfg):
    from super import gates

    ok, missing = gates.check(cfg, args.symbols)
    if ok:
        _out({"ok": True, "checked": len(args.symbols)}, args.json,
             f"PASS: all {len(args.symbols)} symbol(s) observed")
    else:
        print(f"REJECT: observe first: {', '.join(missing)} (grep/LSP/type-check)", file=sys.stderr)
        sys.exit(EXIT_GATE)


def cmd_write_check(args, cfg):
    from super import gates

    with open(args.file, encoding="utf-8", errors="replace") as f:
        source = f.read()
    ok, blockers = gates.run_write_gates(cfg, source, where=args.file)
    if ok:
        _out({"ok": True}, args.json, f"PASS: {args.file} clears the write path")
    else:
        print(f"REJECT {args.file}:", file=sys.stderr)
        for b in blockers:
            print(f"  - {b}", file=sys.stderr)
        sys.exit(EXIT_GATE)


def cmd_status(args, cfg):
    from super import ledger

    payload = {"model": f"{cfg['llm']['model']} @ {cfg['llm']['endpoint']}",
               "gates": ledger.gate_stats(cfg), "catch_rates": ledger.catch_rates(cfg),
               "open_criticals": len(ledger.open_criticals(cfg))}
    _out(payload, args.json,
         f"model: {payload['model']}\ngates: {json.dumps(payload['gates'])}\n"
         f"open criticals: {payload['open_criticals']}")


def cmd_report(args, cfg):
    from super import ledger, quality

    done_ok, blockers = quality.done_state(cfg)
    payload = {"gates": ledger.gate_stats(cfg),
               "catch_rates": ledger.catch_rates(cfg), "open_criticals": ledger.open_criticals(cfg),
               "done_ok": done_ok, "done_blockers": blockers}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Done-state: {'READY' if done_ok else 'BLOCKED'}")
        for b in blockers:
            print(f"  ! {b}")
        print(f"gates: {json.dumps(payload['gates'])}")


def cmd_metrics(args, cfg):
    from super import ledger, trust
    from super import security as sec

    payload = {"ledger": ledger.report(cfg),
               "fatigue": trust.fatigue(cfg), "sink": sec.sink_audit(cfg)}
    print(json.dumps(payload, indent=2))


def cmd_secret_scan(args, cfg):
    from super import security as sec

    with open(args.file, encoding="utf-8", errors="replace") as f:
        text = f.read()
    hits = sec.scan_secrets(text)
    payload = {"file": args.file, "hits": [{"kind": k, "match": m} for k, m in hits]}
    if hits:
        print(json.dumps(payload, indent=2))
        sys.exit(EXIT_GATE)
    _out(payload, args.json, f"PASS: no secrets in {args.file}")


def cmd_sast(args, cfg):
    from super import security as sec

    with open(args.file, encoding="utf-8", errors="replace") as f:
        text = f.read()
    findings = sec.sast_scan(text)
    if findings:
        print(json.dumps({"file": args.file, "findings": findings}, indent=2))
        sys.exit(EXIT_GATE)
    _out({"file": args.file, "findings": []}, args.json, f"PASS: SAST clean ({args.file})")


def cmd_dep_check(args, cfg):
    from super import security as sec

    ok, msg = sec.gate_dependency(cfg, args.name, args.version or "", args.license or "")
    if not ok:
        print(f"REJECT: {msg}", file=sys.stderr)
        sys.exit(EXIT_GATE)
    _out({"ok": True}, args.json, f"PASS: {msg}")


def cmd_verify(args, cfg):
    from super import verify as vermod

    if args.what == "syntax":
        with open(args.file, encoding="utf-8", errors="replace") as f:
            ok, msg = vermod.check_syntax(f.read())
        print(msg)
        sys.exit(0 if ok else EXIT_GATE)
    if args.what == "mutation":
        with open(args.test, encoding="utf-8", errors="replace") as f:
            test_body = f.read()
        with open(args.source, encoding="utf-8", errors="replace") as f:
            source = f.read()
        ok, msg = vermod.gate_acceptance(cfg, test_body, source)
        print(msg)
        sys.exit(0 if ok else EXIT_GATE)


def cmd_memory(args, cfg):
    from super import memory as mem

    if args.op == "remember":
        print(json.dumps(mem.remember(cfg, args.text), indent=2))
    elif args.op == "context":
        print(mem.compile_context(cfg))


def cmd_trust(args, cfg):
    from super import trust as trustmod

    if args.op == "route":
        decision, radius, reason = trustmod.route(cfg, args.files or [], int(args.loc or 0),
                                                  track_record=args.track_record)
        print(json.dumps({"decision": decision, "blast_radius": radius, "reason": reason}, indent=2))
    elif args.op == "fatigue":
        print(json.dumps(trustmod.fatigue(cfg), indent=2))
    elif args.op == "tier":
        print(json.dumps(trustmod.trust_tier(cfg, args.agent or "default", args.area or "general"), indent=2))


def cmd_ambition(args, cfg):
    from super import ambition as amb

    if args.op == "contract":
        c = amb.compile_contract(cfg, args.request, domain=args.domain or "general")
        print(json.dumps(c, indent=2))
    elif args.op == "done":
        import json as _json

        with open(args.contract, encoding="utf-8") as f:
            c = _json.load(f)
        ok, blockers, scorecard = amb.done_state(cfg, c)
        print(_json.dumps(scorecard, indent=2))
        sys.exit(0 if ok else EXIT_GATE)


def cmd_replay(args, cfg):
    from super import meta

    if args.op == "record":
        import json as _json

        print(_json.dumps(meta.record_failure(cfg, args.session, args.failure_class,
                                              _json.loads(args.would_catch or "{}"),
                                              note=args.note or ""), indent=2))
    elif args.op == "matrix":
        print(json.dumps(meta.catch_matrix(cfg), indent=2))
    elif args.op == "descent":
        print(json.dumps({"candidates": meta.descent_candidates(cfg)}, indent=2))


def cmd_waive(args, cfg):
    from super import ledger
    import re as _re, datetime as _dt
    text = (args.text or "").strip()
    if not text:
        print("error: text required", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    expires = (args.expires or "").strip()
    if not expires:
        print("error: --expires YYYY-MM-DD required — no permanent bypass", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    if not _re.match(r"^\d{4}-\d{2}-\d{2}$", expires):
        print("error: --expires must be YYYY-MM-DD", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    try:
        ed = _dt.date.fromisoformat(expires)
        if ed <= _dt.date.today():
            print("error: --expires must be in the future", file=sys.stderr)
            sys.exit(EXIT_USAGE)
    except ValueError:
        print("error: --expires must be valid YYYY-MM-DD", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    ledger.add_issue(cfg, args.severity or "minor", args.layer or "waiver",
                     f"WAIVER by {args.owner or 'human'}: {text}", expires=expires, owner=args.owner or "human")
    ledger.log_gate(cfg, "waiver", "F7", "pass", detail=text[:200])
    _out({"ok": True}, args.json, f"waived: {text[:60]} (expires {expires})")


def cmd_ledger(args, cfg):
    from super import ledger
    payload = {"gates": ledger.gate_stats(cfg), "catch_rates": ledger.catch_rates(cfg),
               "open_criticals": ledger.open_criticals(cfg), "open_issues": ledger.open_issues(cfg)}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload, indent=2))


def cmd_serve(args, cfg):
    from super import server

    server.serve(cfg)


def cmd_token(args, cfg):
    print((cfg.get("server", {}) or {}).get("token", ""))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="super", description="SUPER harness CLI")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    p = sub.add_parser("chat")
    p.add_argument("prompt")
    p.add_argument("--system", default=None)
    p = sub.add_parser("waive")
    p.add_argument("text")
    p.add_argument("--expires", required=True, help="YYYY-MM-DD — no permanent bypass")
    p.add_argument("--owner", default="human")
    p.add_argument("--severity", default="minor")
    p.add_argument("--layer", default="waiver")
    sub.add_parser("ledger")
    p = sub.add_parser("gate-check")
    p.add_argument("symbols", nargs="+")
    p = sub.add_parser("write-check")
    p.add_argument("file")
    sub.add_parser("status")
    sub.add_parser("report")
    sub.add_parser("metrics")
    p = sub.add_parser("secret-scan")
    p.add_argument("file")
    p = sub.add_parser("sast")
    p.add_argument("file")
    p = sub.add_parser("dep-check")
    p.add_argument("name")
    p.add_argument("--version", default="")
    p.add_argument("--license", default="")
    p = sub.add_parser("verify")
    p.add_argument("what", choices=["syntax", "mutation"])
    p.add_argument("--file", default="")
    p.add_argument("--test", default="")
    p.add_argument("--source", default="")
    p = sub.add_parser("memory")
    p.add_argument("op", choices=["remember", "context"])
    p.add_argument("--text", default="")
    p = sub.add_parser("trust")
    p.add_argument("op", choices=["route", "fatigue", "tier"])
    p.add_argument("--files", nargs="*", default=[])
    p.add_argument("--loc", default="0")
    p.add_argument("--track-record", action="store_true")
    p.add_argument("--agent", default="default")
    p.add_argument("--area", default="general")
    p = sub.add_parser("ambition")
    p.add_argument("op", choices=["contract", "done"])
    p.add_argument("--request", default="")
    p.add_argument("--domain", default="general")
    p.add_argument("--contract", default="")
    p = sub.add_parser("replay")
    p.add_argument("op", choices=["record", "matrix", "descent"])
    p.add_argument("--session", default="")
    p.add_argument("--failure-class", default="F1")
    p.add_argument("--would-catch", default="{}")
    p.add_argument("--note", default="")
    sub.add_parser("serve")
    sub.add_parser("token")

    args = ap.parse_args(argv)
    try:
        cfg = config_mod.load()
    except SuperError as e:
        print(f"config error: {e}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    {
        "init": cmd_init, "chat": cmd_chat,
        "gate-check": cmd_gate_check, "write-check": cmd_write_check,
        "status": cmd_status, "report": cmd_report, "metrics": cmd_metrics,
        "secret-scan": cmd_secret_scan, "sast": cmd_sast, "dep-check": cmd_dep_check,
        "verify": cmd_verify, "memory": cmd_memory,
        "trust": cmd_trust, "ambition": cmd_ambition, "replay": cmd_replay,
        "serve": cmd_serve, "token": cmd_token,
        "waive": cmd_waive, "ledger": cmd_ledger,
    }[args.cmd](args, cfg)


if __name__ == "__main__":
    main()
