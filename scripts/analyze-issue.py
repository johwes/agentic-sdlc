#!/usr/bin/env python3
"""Fetch a GitHub issue, run in-cell triage (glm-5.3-flash), write tasks/inbox frame.

Two-command demo (no polling)::
  python3 scripts/analyze-issue.py --repo https://github.com/johwes/tic-tac-toe.git --issue-id 1
  python3 temporal/starter.py tasks/inbox/TASK-1.json

Triage runs in-cell via opencode --model opencode-go/glm-5.3-flash with
prompts/triage_contract.txt + issue JSON. On --dry-run no cell is created.
Output is a spec-compliant current_task.json for the fix agent
(opencode-go/muse-spark-1.3-contributor, adaptive retry).
Host gh issue comment is done outside the cell (host gh, not policy-bound).

See specs/02-control-plane.md (issue ingest), specs/04-worker-cell.md (triage
tier), specs/07-contracts.md (frame shape).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any

# Reuse child helpers for repo URL validation and workspace prep when available.
try:
    # When run as `python3 scripts/analyze-issue.py` the scripts/ dir is not a package
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "temporal"))
    from child import validate_repo_url as _validate_repo_url
    from child import prepare_workspace, new_workspace_dir, spawn_script_path, run_spawn
    from child import SPAWN_CREATE, SPAWN_DESTROY
except ImportError:
    _validate_repo_url = None  # type: ignore
    prepare_workspace = None  # type: ignore
    new_workspace_dir = None  # type: ignore
    spawn_script_path = None  # type: ignore
    run_spawn = None  # type: ignore

TRIAGE_MODEL_DEFAULT = "opencode-go/glm-5.3-flash"
TRIAGE_CONTRACT_DEFAULT = "prompts/triage_contract.txt"
TRIAGE_TIMEOUT_DEFAULT = 300
INBOX_DIR_DEFAULT = "tasks/inbox"


def _repo_slug(url: str) -> str | None:
    try:
        path = str(url).strip().split("://", 1)[1].split("/", 1)[1]
    except IndexError:
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return f"{parts[0]}/{repo}" if parts[0] and repo else None


def _validate_repo(url: Any) -> str | None:
    if _validate_repo_url is not None:
        return _validate_repo_url(url)
    if not isinstance(url, str) or not url.strip():
        return "repo_url must be a non-empty string"
    u = url.strip()
    if not u.startswith("https://"):
        return f"repo_url must be public https (got {u!r})"
    host = u[len("https://"):].split("/", 1)[0]
    if "@" in host:
        return "repo_url must not carry credentials"
    return None


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    parts = [p for p in slug.split("-") if p]
    return "-".join(parts[:4]) or "issue-fix"


def _fetch_issue(repo_url: str, issue_id: int, runner=None) -> dict[str, Any]:
    """Fetch issue via gh. Runner injects subprocess.run for tests."""
    run = runner or subprocess.run
    slug = _repo_slug(repo_url)
    if not slug:
        raise ValueError(f"cannot derive owner/repo from {repo_url!r}")
    # Prefer `gh issue view --json` (no API pagination, host auth via gh)
    r = run(
        ["gh", "issue", "view", str(issue_id), "--repo", slug, "--json", "number,title,body,labels,url,state"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r.returncode == 0 and r.stdout.strip():
        try:
            data = json.loads(r.stdout)
            if isinstance(data, dict) and "title" in data:
                return data
        except json.JSONDecodeError:
            pass
    # Fallback to gh api
    r2 = run(
        ["gh", "api", f"repos/{slug}/issues/{issue_id}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r2.returncode != 0:
        raise RuntimeError(f"gh fetch failed: {(r2.stderr or r.stdout or '').strip()}"[:2000])
    try:
        data = json.loads(r2.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"gh api invalid JSON: {e}")
    if not isinstance(data, dict):
        raise RuntimeError("gh api returned non-object")
    # Normalize gh api shape to view shape
    labels = data.get("labels") or []
    if labels and isinstance(labels[0], dict):
        labels = [l.get("name", "") for l in labels]
    return {
        "number": data.get("number", issue_id),
        "title": data.get("title") or "",
        "body": data.get("body") or "",
        "labels": labels,
        "url": data.get("html_url") or data.get("url") or "",
        "state": data.get("state") or "open",
    }


def _triage_contract_path(explicit: str | None = None) -> str:
    for cand in [explicit, os.environ.get("TRIAGE_CONTRACT"), TRIAGE_CONTRACT_DEFAULT]:
        if cand and cand.strip() and Path(cand.strip()).is_file():
            return cand.strip()
    # Repo fallback
    try:
        here = Path(__file__).resolve()
        cand = here.parent.parent / "prompts" / "triage_contract.txt"
        if cand.is_file():
            return str(cand)
    except Exception:
        pass
    return TRIAGE_CONTRACT_DEFAULT


def _deterministic_triage(issue: dict[str, Any], repo_url: str) -> dict[str, Any]:
    """Fallback curate when no LLM or dry-run. Minimal, repo-aware."""
    title = str(issue.get("title") or "Fix issue").strip() or "Fix issue"
    body = str(issue.get("body") or "")
    slug = _slugify(title)
    # Heuristic tactile + paths
    if "tic-tac-toe" in repo_url or "tictactoe" in body.lower():
        allowed = ["tictactoe.js"]
        forbidden = ["tictactoe.test.js", ".task/**"]
        tactile = "node --test tictactoe.test.js"
    else:
        # Generic: look for language hints
        low = (title + " " + body).lower()
        if "pytest" in low or ".py" in low or "python" in low:
            tactile = "pytest"
            allowed = ["src/**"]
        elif "npm" in low or "jest" in low or ".ts" in low:
            tactile = "npm test"
            allowed = ["src/**"]
        else:
            tactile = "pytest"
            allowed = ["src/**"]
        forbidden = [".task/**"]
    # Acceptance: first non-empty body lines as criteria, cap 2
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    criteria = []
    for l in lines[:2]:
        if len(l) > 10:
            criteria.append(l[:160])
    if not criteria:
        criteria = [title[:160]]
    criteria = criteria[:2] + ["tactile_command passes with exit code 0", "No files outside allowed_paths are modified"]
    criteria = criteria[:3]
    return {
        "title": title[:200],
        "acceptance_criteria": criteria,
        "allowed_paths": allowed,
        "forbidden_paths": forbidden,
        "tactile_command": tactile,
        "slug": slug,
        "triage_summary": f"Deterministic triage: {title[:120]}",
    }


def _parse_triage_output(text: str) -> dict[str, Any] | None:
    """Extract JSON from LLM output. Last JSON object wins."""
    # Try whole blob
    try:
        obj = json.loads(text.strip())
        if isinstance(obj, dict) and "title" in obj:
            return obj
    except Exception:
        pass
    # Find JSON code block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "title" in obj:
                return obj
        except Exception:
            pass
    # Line-delimited JSON
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and "title" in obj:
                    return obj
            except Exception:
                continue
    return None


def _curate_triage_output(raw: dict[str, Any], issue: dict[str, Any], repo_url: str) -> dict[str, Any]:
    """Validate and fill defaults for triage JSON."""
    det = _deterministic_triage(issue, repo_url)
    out: dict[str, Any] = {}
    out["title"] = str(raw.get("title") or det["title"]).strip()[:200] or det["title"]
    ac = raw.get("acceptance_criteria")
    if isinstance(ac, list) and ac and all(isinstance(x, str) for x in ac):
        ac = [str(x).strip()[:200] for x in ac if str(x).strip()]
        if len(ac) >= 1:
            # Ensure tactile + allowed_paths criteria present
            has_tactile = any("tactile" in x.lower() for x in ac)
            has_allowed = any("allowed_paths" in x.lower() or "outside" in x.lower() for x in ac)
            if not has_tactile:
                ac.append("tactile_command passes with exit code 0")
            if not has_allowed:
                ac.append("No files outside allowed_paths are modified")
            out["acceptance_criteria"] = ac[:4]
        else:
            out["acceptance_criteria"] = det["acceptance_criteria"]
    else:
        out["acceptance_criteria"] = det["acceptance_criteria"]
    ap = raw.get("allowed_paths")
    out["allowed_paths"] = list(ap) if isinstance(ap, list) and ap and all(isinstance(x, str) for x in ap) else det["allowed_paths"]
    fp = raw.get("forbidden_paths")
    out["forbidden_paths"] = list(fp) if isinstance(fp, list) and fp and all(isinstance(x, str) for x in fp) else det["forbidden_paths"]
    tc = raw.get("tactile_command")
    out["tactile_command"] = str(tc).strip()[:200] if isinstance(tc, str) and tc.strip() else det["tactile_command"]
    out["slug"] = str(raw.get("slug") or det["slug"]).strip()[:40] or det["slug"]
    out["slug"] = _slugify(out["slug"])
    out["triage_summary"] = str(raw.get("triage_summary") or det["triage_summary"]).strip()[:500] or det["triage_summary"]
    return out


def _build_frame(triage: dict[str, Any], issue: dict[str, Any], repo_url: str, issue_id: int) -> dict[str, Any]:
    task_id = f"TASK-{issue_id}"
    slug = triage.get("slug") or _slugify(str(issue.get("title") or "fix"))
    return {
        "task_id": task_id,
        "title": triage["title"],
        "acceptance_criteria": triage["acceptance_criteria"],
        "repo_url": repo_url.strip(),
        "target_branch": f"feat/{task_id.lower()}-{slug}".strip(),
        "allowed_paths": triage["allowed_paths"],
        "forbidden_paths": triage["forbidden_paths"],
        "sensor_context": [
            {
                "tool_name": "GitHubIssue",
                "rule_id": f"issue-{issue_id}",
                "file_path": (triage["allowed_paths"][0] if triage["allowed_paths"] else "unknown"),
                "line_number": 1,
                "message": f"GitHub issue #{issue_id}: {issue.get('title','')}\n{str(issue.get('body',''))[:1000]}\nTriage: {triage.get('triage_summary','')}"[:2000],
            }
        ],
        "attempt": 1,
        "max_attempts": 5,
        "tactile_command": triage["tactile_command"],
        "tactile_timeout_seconds": 120,
        # retry_strategy omitted → adaptive default
    }


# --- In-cell triage via openshell ---

def _run_triage_in_cell(
    issue: dict[str, Any],
    repo_url: str,
    model: str,
    triage_contract: str,
    timeout: int,
) -> tuple[dict[str, Any], str]:
    """Create a triage cell, run glm-5.3-flash, return (parsed_json, raw_output).

    Cell lifecycle: clone repo_url into workspace, create cell, upload prompt,
    exec opencode, download output, destroy. Raises on failure.
    """
    if prepare_workspace is None or new_workspace_dir is None:
        raise RuntimeError("temporal/child helpers not importable — is repo layout intact?")

    # Prepare workspace (clone target repo; triage needs repo context for path hints)
    # Use issue title slug as task for cell naming
    slug = _slugify(str(issue.get("title") or "triage"))
    task_id_tri = f"TRIAGE-{issue.get('number', 0)}"
    workspace = new_workspace_dir(f"triage-{issue.get('number', 0)}")
    # Minimal frame to drive prepare_workspace (needs repo_url + target_branch)
    fake_frame = {"repo_url": repo_url.strip(), "target_branch": "main"}
    try:
        prepare_workspace(fake_frame, workspace)
    except Exception as e:
        raise RuntimeError(f"triage workspace clone failed: {e}")

    # Build triage prompt file (contract + issue JSON)
    contract_text = Path(triage_contract).read_text(encoding="utf-8", errors="replace")
    issue_payload = json.dumps(issue, indent=2, ensure_ascii=False)
    prompt_text = contract_text.rstrip() + "\n\nISSUE JSON:\n" + issue_payload + "\n"
    prompt_tmp = tempfile.mktemp(suffix="-triage-prompt.txt")
    Path(prompt_tmp).write_text(prompt_text, encoding="utf-8")

    # Create cell
    env_create = dict(os.environ)
    env_create["TASK_ID"] = task_id_tri
    env_create["WORKSPACE_DIR"] = workspace
    # Triage-specific env: caller may override provider; default opencode-go
    r = run_spawn(SPAWN_CREATE, env_create)
    if r.returncode != 0:
        raise RuntimeError(f"spawn-cell create failed: {(r.stderr or '').strip()}"[:2000])
    cell = (r.stdout or "").strip().splitlines()[-1].strip()
    if not cell:
        raise RuntimeError("spawn-cell create printed no cell name")

    # Upload prompt
    import subprocess as _sp

    # Use upload_file_to semantics via openshell directly (avoid importing spawn internals)
    # Reuse spawn-cell upload path: upload to /sandbox/.task/ then mv to triage_prompt.txt
    triage_remote = "triage_prompt.txt"
    cell_repo = os.environ.get("CELL_REPO_PATH", "/sandbox/repo")
    try:
        # Ensure dir
        _sp.run(
            [os.environ.get("OPENSHELL_BIN", "openshell"), "sandbox", "exec", "-n", cell, "--workdir", "/sandbox", "--timeout", "60", "--", "mkdir", "-p", ".task"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Upload
        _sp.run(
            [os.environ.get("OPENSHELL_BIN", "openshell"), "sandbox", "upload", cell, prompt_tmp, "/sandbox/.task/"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Handle dir-semantics mv when basename != remote
        base = Path(prompt_tmp).name
        if base != triage_remote:
            _sp.run(
                [os.environ.get("OPENSHELL_BIN", "openshell"), "sandbox", "exec", "-n", cell, "--workdir", "/sandbox/.task", "--timeout", "60", "--", "mv", "--", base, triage_remote],
                capture_output=True,
                text=True,
                timeout=60,
            )
        else:
            # Already uploaded as basename; rename if needed
            _sp.run(
                [os.environ.get("OPENSHELL_BIN", "openshell"), "sandbox", "exec", "-n", cell, "--workdir", "/sandbox/.task", "--timeout", "60", "--", "mv", "--", base, triage_remote],
                capture_output=True,
                text=True,
                timeout=60,
            )
    except Exception as e:
        try:
            run_spawn(SPAWN_DESTROY, {"CELL": cell})
        except Exception:
            pass
        raise RuntimeError(f"triage prompt upload failed: {e}")

    # Exec triage: opencode run --auto --model glm-5.3-flash
    prompt_in_cell = "/sandbox/.task/triage_prompt.txt"
    # Read prompt via cat inside exec to avoid shell quoting issues
    # Build opencode argv: opencode run --auto --model <model> "$(cat prompt)"
    # Simpler: exec a shell that cats the file and pipes to opencode? But spec says
    # opencode run --auto --model <id> "<prompt>" with prompt as last arg.
    # We will cat the file host-side and pass as arg via sandbox exec with prompt content.
    # However prompt may be large; we already have it in cell, so run: sh -c 'opencode run --auto --model X "$(cat /sandbox/.task/triage_prompt.txt)"'
    exec_timeout = timeout
    raw_output = ""
    try:
        # Use openshell sandbox exec with shell wrapper
        r2 = _sp.run(
            [
                os.environ.get("OPENSHELL_BIN", "openshell"),
                "sandbox",
                "exec",
                "-n",
                cell,
                "--workdir",
                "/sandbox",
                "--timeout",
                str(exec_timeout),
                "--",
                "bash",
                "-c",
                f'opencode run --auto --model {model} "$(cat {prompt_in_cell})"',
            ],
            capture_output=True,
            text=True,
            timeout=exec_timeout + 60,
        )
        raw_output = (r2.stdout or "") + "\n" + (r2.stderr or "")
        if r2.returncode != 0 and not raw_output.strip():
            raise RuntimeError(f"triage exec failed: {(r2.stderr or '').strip()}"[:2000])
    finally:
        # Destroy cell (best-effort, never orphan)
        try:
            run_spawn(SPAWN_DESTROY, {"CELL": cell})
        except Exception:
            pass
        try:
            Path(prompt_tmp).unlink(missing_ok=True)
        except Exception:
            pass
        # Workspace temp dir lingers for debugging (like spawn-cell)

    parsed = _parse_triage_output(raw_output)
    if parsed is None:
        raise RuntimeError(f"triage output not JSON: {raw_output[:1000]}")
    return parsed, raw_output


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch GitHub issue, triage in-cell (glm-5.3-flash), write tasks/inbox frame")
    p.add_argument("--repo", required=True, help="Target repo URL https://github.com/owner/repo.git (public https)")
    p.add_argument("--issue-id", required=True, type=int, help="GitHub issue number")
    p.add_argument("--out", required=False, default=None, help="Output inbox path (default tasks/inbox/TASK-<n>.json)")
    p.add_argument("--model", required=False, default=TRIAGE_MODEL_DEFAULT, help="Triage model (default opencode-go/glm-5.3-flash)")
    p.add_argument("--triage-contract", required=False, default=None, help="Triage prompt path (default prompts/triage_contract.txt)")
    p.add_argument("--triage-timeout", required=False, type=int, default=TRIAGE_TIMEOUT_DEFAULT, help="Cell exec timeout secs (default 300)")
    p.add_argument("--dry-run", action="store_true", help="Skip cell creation; deterministic triage only (offline)")
    p.add_argument("--no-comment", action="store_true", help="Skip gh issue comment")
    args = p.parse_args()

    err = _validate_repo(args.repo)
    if err is not None:
        print(f"Invalid --repo: {err}", file=sys.stderr)
        return 2

    # Fetch issue
    try:
        issue = _fetch_issue(args.repo.strip(), int(args.issue_id))
    except Exception as e:
        print(f"Fetch issue failed: {e}", file=sys.stderr)
        return 1
    print(f"Fetched issue #{issue.get('number')} \"{issue.get('title','')}\" state={issue.get('state','')} url={issue.get('url','')}", file=sys.stderr)

    # Dedup: inbox file exists?
    out_path = Path(args.out) if args.out else Path(INBOX_DIR_DEFAULT) / f"TASK-{issue.get('number', args.issue_id)}.json"
    if out_path.exists():
        print(f"Refusing: inbox file already exists {out_path} (already triaged?) — remove it or use --out", file=sys.stderr)
        return 0
    ledger = Path("tasks/ledger.md")
    if ledger.is_file():
        try:
            txt = ledger.read_text(encoding="utf-8")
            if f"| TASK-{issue.get('number', args.issue_id)} |" in txt and "promoted" in txt:
                print(f"Ledger already has TASK-{issue.get('number')} promoted — skipping", file=sys.stderr)
                return 0
        except Exception:
            pass

    # Triage
    contract = _triage_contract_path(args.triage_contract)
    triage_raw: dict[str, Any]
    triage_text = ""
    if args.dry_run:
        triage_raw = _deterministic_triage(issue, args.repo.strip())
        triage_text = json.dumps(triage_raw, indent=2)
        print(f"Dry-run triage (deterministic): {triage_text}", file=sys.stderr)
    else:
        try:
            # Check openshell available
            if not os.environ.get("OPENSHELL_BIN") and not subprocess.run(["which", "openshell"], capture_output=True).returncode == 0:
                # which failure is okay, openshell may still be on PATH via other means
                pass
            triage_raw, triage_text = _run_triage_in_cell(issue, args.repo.strip(), args.model, contract, int(args.triage_timeout))
            print(f"Triage cell output ({args.model}): {triage_text[:500]}", file=sys.stderr)
        except Exception as e:
            print(f"Triage in-cell failed: {e}\nFalling back to deterministic triage", file=sys.stderr)
            triage_raw = _deterministic_triage(issue, args.repo.strip())
            triage_text = json.dumps(triage_raw, indent=2)

    curated = _curate_triage_output(triage_raw, issue, args.repo.strip())
    print(f"Curated: {json.dumps(curated, indent=2)}", file=sys.stderr)

    frame = _build_frame(curated, issue, args.repo.strip(), int(issue.get("number", args.issue_id)))
    # Validate frame minimal via parent load check
    try:
        # Light check: required fields present
        missing = [f for f in ["task_id", "title", "acceptance_criteria", "repo_url", "target_branch", "allowed_paths", "forbidden_paths", "sensor_context", "attempt", "max_attempts", "tactile_command"] if f not in frame]
        if missing:
            raise ValueError(f"frame missing {missing}")
    except Exception as e:
        print(f"Frame validation failed: {e}", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(frame, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    print(f"Wrote {out_path} (task_id {frame['task_id']}, branch {frame['target_branch']}, tactile {frame['tactile_command']!r})", file=sys.stderr)
    # Describe like starter --dry-run
    try:
        sys.path.insert(0, "temporal")
        from parent import load_frame as _lf
        f2, e2 = _lf(str(out_path))
        if e2:
            print(f"Load check failed: {e2}", file=sys.stderr)
        else:
            print(f"dry-run: would open ParentWorkflow (workflow_id=parent-{f2['task_id']}, task_queue='agentic-sdlc-dev') from {out_path} (attempt {f2['attempt']}/{f2['max_attempts']}, branch {f2['target_branch']})", file=sys.stderr)
    except Exception:
        pass

    # Host gh issue comment (outside policy)
    if not args.no_comment:
        slug = _repo_slug(args.repo.strip())
        summary = curated.get("triage_summary", "")
        body = textwrap.dedent(f"""\
            Triaged → `{frame['task_id']}` (branch `{frame['target_branch']}`)

            {summary}

            Frame wrote to `{out_path}` — run `python3 temporal/starter.py {out_path}` to fix.
            *Model: triage {args.model} → fix opencode-go/muse-spark-1.3-contributor (adaptive).*
            """)
        try:
            r = subprocess.run(
                ["gh", "issue", "comment", str(issue.get("number", args.issue_id)), "--repo", slug or "", "--body", body],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode != 0:
                print(f"gh issue comment failed (non-fatal): {(r.stderr or '').strip()}", file=sys.stderr)
            else:
                print(f"Commented on issue #{issue.get('number')} ({slug})", file=sys.stderr)
        except Exception as e:
            print(f"Comment failed (non-fatal): {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
