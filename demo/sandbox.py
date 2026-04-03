"""Custom Scripts Sandbox for Zen Den — AI-generated automation scripts.

Users describe what they want in plain English, the AI generates a Python
function, the user reviews and approves it, and it gets saved and loaded
at runtime inside a restricted execution environment.
"""

import ast
import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("zen.sandbox")

# ---------------------------------------------------------------------------
# Data directory resolution (PyInstaller-aware)
# ---------------------------------------------------------------------------

def _data_dir():
    if getattr(sys, "_MEIPASS", None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


_SCRIPTS_FILE = "custom_scripts.json"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def load_scripts() -> list:
    path = _data_dir() / _SCRIPTS_FILE
    if not path.exists():
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load scripts: %s", exc)
        return []


def save_scripts(scripts: list):
    path = _data_dir() / _SCRIPTS_FILE
    with open(path, "w") as f:
        json.dump(scripts, f, indent=2)


def get_script(script_id: str) -> dict | None:
    for s in load_scripts():
        if s.get("id") == script_id:
            return s
    return None


def create_script(script: dict) -> dict:
    scripts = load_scripts()
    now = datetime.now(timezone.utc).isoformat()
    script.setdefault("id", f"script_{int(time.time())}")
    script.setdefault("enabled", True)
    script.setdefault("approved", False)
    script.setdefault("created", now)
    script.setdefault("last_run", None)
    script.setdefault("run_count", 0)
    script.setdefault("trigger", "email")
    script.setdefault("version", 1)
    script.setdefault("history", [])
    scripts.append(script)
    save_scripts(scripts)
    return script


def update_script(script_id: str, updates: dict) -> dict | None:
    scripts = load_scripts()
    for s in scripts:
        if s.get("id") == script_id:
            old_code = s.get("code")
            s.update(updates)
            if "code" in updates and updates["code"] != old_code:
                s["version"] = s.get("version", 1) + 1
                s["history"] = s.get("history", [])
                s["history"].append({
                    "version": s["version"] - 1,
                    "code": old_code,
                    "changed": datetime.now(timezone.utc).isoformat(),
                })
            save_scripts(scripts)
            return s
    return None


def delete_script(script_id: str) -> bool:
    scripts = load_scripts()
    before = len(scripts)
    scripts = [s for s in scripts if s.get("id") != script_id]
    if len(scripts) < before:
        save_scripts(scripts)
        return True
    return False


def toggle_script(script_id: str) -> dict | None:
    scripts = load_scripts()
    for s in scripts:
        if s.get("id") == script_id:
            s["enabled"] = not s.get("enabled", True)
            save_scripts(scripts)
            return s
    return None


# ---------------------------------------------------------------------------
# Code Generation
# ---------------------------------------------------------------------------

_CONTEXT_FIELDS = (
    "sender, sender_name, subject, body, channel, client_name, "
    "timestamp, message_type, tags"
)

_ALLOWED_ACTIONS = """\
  - {"action": "tag", "value": "<label>"}
  - {"action": "reply", "text": "<response text>"}
  - {"action": "forward", "to": "<recipient>", "text": "<optional note>"}
  - {"action": "escalate", "reason": "<reason>"}
  - {"action": "skip"}
  - {"action": "log", "message": "<message>"}"""


def generate_script_prompt(user_request: str) -> str:
    return f"""\
Write a single Python function with the signature:

    def run(context):

The `context` parameter is a dict with these keys:
    {_CONTEXT_FIELDS}

Based on the following user request, write the function body:

    \"{user_request}\"

Rules:
1. Return None if no action is needed.
2. Otherwise return ONE of these action dicts:
{_ALLOWED_ACTIONS}
3. Use ONLY the Python standard library. No imports allowed.
4. No file I/O, no network calls, no subprocess, no exec/eval.
5. Keep the function short and readable (under 30 lines).
6. Use .get() for safe dict access.
7. Use .lower() for case-insensitive comparisons.
8. Return ONLY the function code — no markdown fences, no explanation.
"""


def generate_placeholder_script(user_request: str) -> str:
    keywords = _extract_keywords(user_request)
    lower_req = user_request.lower()

    action = "tag"
    action_detail = '"value": "flagged"'
    if any(w in lower_req for w in ("reply", "respond", "answer")):
        action = "reply"
        action_detail = '"text": "Noted — we\'ll follow up shortly."'
    elif any(w in lower_req for w in ("forward", "send to", "route")):
        action = "forward"
        action_detail = '"to": "team@example.com", "text": "Forwarded per rule"'
    elif any(w in lower_req for w in ("escalate", "urgent", "priority")):
        action = "escalate"
        action_detail = '"reason": "Matched escalation rule"'
    elif any(w in lower_req for w in ("skip", "ignore", "discard")):
        action = "skip"
        action_detail = ""
    elif any(w in lower_req for w in ("log", "record", "track")):
        action = "log"
        action_detail = '"message": "Rule matched"'

    if keywords:
        conditions = " or ".join(
            f"'{kw}' in sender or '{kw}' in subject or '{kw}' in body"
            for kw in keywords[:3]
        )
    else:
        conditions = "True  # TODO: add your condition"

    action_dict = f'{{"action": "{action}", {action_detail}}}' if action_detail else f'{{"action": "{action}"}}'

    return (
        "def run(context):\n"
        "    sender = context.get('sender', '').lower()\n"
        "    body = context.get('body', '').lower()\n"
        "    subject = context.get('subject', '').lower()\n"
        f"    if {conditions}:\n"
        f"        return {action_dict}\n"
        "    return None\n"
    )


def _extract_keywords(text: str) -> list[str]:
    """Pull likely domain-relevant keywords from a user request."""
    stop = {
        "i", "want", "to", "the", "a", "an", "and", "or", "if", "is", "it",
        "that", "this", "from", "in", "on", "for", "with", "as", "by", "of",
        "my", "me", "any", "all", "when", "emails", "email", "messages",
        "message", "auto", "tag", "reply", "forward", "escalate", "skip",
        "should", "be", "are", "not", "do", "does", "will", "can", "has",
        "have", "been", "was", "were", "about", "check", "detect", "set",
    }
    words = []
    for w in text.lower().split():
        cleaned = w.strip(".,!?;:\"'()[]{}").replace("'s", "")
        if cleaned and cleaned not in stop and len(cleaned) > 2:
            words.append(cleaned)
    return words


# ---------------------------------------------------------------------------
# Sandbox Execution — Validation
# ---------------------------------------------------------------------------

_FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "open", "compile", "__import__",
    "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "dir",
    "breakpoint", "exit", "quit",
    "input", "print",                 # not dangerous, but unwanted in sandbox
    "memoryview", "bytearray",
})

_FORBIDDEN_ATTR_PREFIXES = ("__",)
_ALLOWED_DUNDERS = frozenset({"__init__", "__str__", "__repr__"})

_SAFE_BUILTINS = {
    "True": True, "False": False, "None": None,
    "str": str, "int": int, "float": float,
    "list": list, "dict": dict, "bool": bool, "tuple": tuple, "set": set,
    "len": len, "range": range, "min": min, "max": max,
    "abs": abs, "round": round, "sorted": sorted,
    "enumerate": enumerate, "zip": zip,
    "any": any, "all": all,
    "isinstance": isinstance, "type": type,
    "map": map, "filter": filter,
    "reversed": reversed,
    "sum": sum,
    "chr": chr, "ord": ord,
}


class _CodeValidator(ast.NodeVisitor):
    """Walk the AST and collect security violations."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self._has_run = False

    # -- top-level checks ---------------------------------------------------

    def check_module(self, tree: ast.Module):
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                self._has_run = True
                args = node.args
                n_params = len(args.args) + len(args.posonlyargs)
                if n_params != 1:
                    self.errors.append(
                        "run() must accept exactly one parameter (context)"
                    )

        if not self._has_run:
            self.errors.append("Code must define a function named run(context)")

        total_lines = max(
            (getattr(n, "end_lineno", 0) or 0) for n in ast.walk(tree)
        ) if list(ast.walk(tree)) else 0
        if total_lines > 100:
            self.warnings.append(f"Code is {total_lines} lines — consider simplifying")

        self.generic_visit(tree)

    # -- forbidden constructs -----------------------------------------------

    def visit_Import(self, node):  # noqa: N802
        self.errors.append(
            f"Imports are not allowed (line {node.lineno})"
        )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):  # noqa: N802
        self.errors.append(
            f"Imports are not allowed: 'from {node.module} ...' (line {node.lineno})"
        )
        self.generic_visit(node)

    def visit_Call(self, node):  # noqa: N802
        name = self._call_name(node)
        if name in _FORBIDDEN_NAMES:
            self.errors.append(
                f"Calling '{name}' is forbidden (line {node.lineno})"
            )
        if name in ("os.system", "os.popen", "subprocess.run",
                     "subprocess.call", "subprocess.Popen",
                     "subprocess.check_output"):
            self.errors.append(
                f"System command '{name}' is forbidden (line {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Attribute(self, node):  # noqa: N802
        attr = node.attr
        if attr.startswith("__") and attr.endswith("__") and attr not in _ALLOWED_DUNDERS:
            self.errors.append(
                f"Access to dunder '{attr}' is forbidden (line {node.lineno})"
            )
        if attr.startswith("__") and not attr.endswith("__"):
            self.errors.append(
                f"Access to name-mangled attribute '{attr}' is forbidden "
                f"(line {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Global(self, node):  # noqa: N802
        self.errors.append(
            f"'global' statement is forbidden (line {node.lineno})"
        )
        self.generic_visit(node)

    def visit_Nonlocal(self, node):  # noqa: N802
        self.warnings.append(
            f"'nonlocal' usage at line {node.lineno} — review carefully"
        )
        self.generic_visit(node)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            parts = []
            current = func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""


def validate_code(code: str) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {
            "valid": False,
            "errors": [f"Syntax error: {exc.msg} (line {exc.lineno})"],
            "warnings": [],
        }

    validator = _CodeValidator()
    validator.check_module(tree)
    errors.extend(validator.errors)
    warnings.extend(validator.warnings)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Sandbox Execution — Runtime
# ---------------------------------------------------------------------------

def execute_script(script_id: str, context: dict, timeout: float = 2.0) -> dict:
    script = get_script(script_id)
    if script is None:
        return {"success": False, "result": None,
                "error": f"Script '{script_id}' not found", "execution_time_ms": 0}

    code = script.get("code", "")
    check = validate_code(code)
    if not check["valid"]:
        return {"success": False, "result": None,
                "error": f"Validation failed: {'; '.join(check['errors'])}",
                "execution_time_ms": 0}

    namespace: dict = {"__builtins__": dict(_SAFE_BUILTINS)}

    try:
        exec(compile(code, f"<sandbox:{script_id}>", "exec"), namespace)  # noqa: S102
    except Exception as exc:
        return {"success": False, "result": None,
                "error": f"Compilation error: {exc}", "execution_time_ms": 0}

    run_fn = namespace.get("run")
    if not callable(run_fn):
        return {"success": False, "result": None,
                "error": "No callable run() found after compilation",
                "execution_time_ms": 0}

    result_box: list = []
    error_box: list = []

    def _target():
        try:
            result_box.append(run_fn(dict(context)))
        except Exception as exc:
            error_box.append(str(exc))

    t0 = time.perf_counter()
    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    if thread.is_alive():
        return {"success": False, "result": None,
                "error": f"Script timed out after {timeout}s",
                "execution_time_ms": elapsed_ms}

    if error_box:
        return {"success": False, "result": None,
                "error": error_box[0], "execution_time_ms": elapsed_ms}

    return {
        "success": True,
        "result": result_box[0] if result_box else None,
        "error": None,
        "execution_time_ms": elapsed_ms,
    }


def run_all_scripts(context: dict, trigger: str = "email") -> list[dict]:
    scripts = load_scripts()
    results = []
    now = datetime.now(timezone.utc).isoformat()
    changed = False

    for s in scripts:
        if not s.get("enabled") or not s.get("approved"):
            continue
        if s.get("trigger") != trigger:
            continue

        outcome = execute_script(s["id"], context)
        outcome["script_id"] = s["id"]
        outcome["script_name"] = s.get("name", "")
        results.append(outcome)

        s["run_count"] = s.get("run_count", 0) + 1
        s["last_run"] = now
        changed = True

    if changed:
        save_scripts(scripts)

    return results


# ---------------------------------------------------------------------------
# Template Scripts Library
# ---------------------------------------------------------------------------

def get_script_templates() -> list[dict]:
    return [
        {
            "id": "template_tag_domain",
            "name": "Tag by sender domain",
            "description": "Tag messages based on the sender's email domain.",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    sender = context.get('sender', '').lower()\n"
                "    domain_tags = {\n"
                "        'gmail.com': 'personal',\n"
                "        'yahoo.com': 'personal',\n"
                "        'outlook.com': 'personal',\n"
                "    }\n"
                "    for domain, tag in domain_tags.items():\n"
                "        if domain in sender:\n"
                "            return {'action': 'tag', 'value': tag}\n"
                "    return {'action': 'tag', 'value': 'business'}\n"
            ),
        },
        {
            "id": "template_priority_keywords",
            "name": "Priority by keywords",
            "description": "Escalate if urgent keywords are detected in the subject or body.",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    subject = context.get('subject', '').lower()\n"
                "    body = context.get('body', '').lower()\n"
                "    text = subject + ' ' + body\n"
                "    urgent = ['asap', 'urgent', 'critical', 'emergency',\n"
                "              'immediately', 'deadline', 'p0', 'blocker']\n"
                "    for word in urgent:\n"
                "        if word in text:\n"
                "            return {'action': 'escalate',\n"
                "                    'reason': 'Urgent keyword: ' + word}\n"
                "    return None\n"
            ),
        },
        {
            "id": "template_auto_reply_status",
            "name": "Auto-reply to status checks",
            "description": "Reply to 'is X on?' or 'are you available?' messages automatically.",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    body = context.get('body', '').lower()\n"
                "    subject = context.get('subject', '').lower()\n"
                "    text = subject + ' ' + body\n"
                "    status_phrases = ['is this on', 'are you available',\n"
                "                      'are you there', 'is anyone there',\n"
                "                      'status check', 'still active']\n"
                "    for phrase in status_phrases:\n"
                "        if phrase in text:\n"
                "            return {'action': 'reply',\n"
                "                    'text': 'Yes — we are active and will '\n"
                "                            'get back to you shortly!'}\n"
                "    return None\n"
            ),
        },
        {
            "id": "template_business_hours",
            "name": "Business hours filter",
            "description": "Only process messages during business hours (9-17 UTC).",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    ts = context.get('timestamp', '')\n"
                "    if not ts or len(ts) < 13:\n"
                "        return None\n"
                "    try:\n"
                "        hour = int(ts[11:13])\n"
                "    except (ValueError, IndexError):\n"
                "        return None\n"
                "    if hour < 9 or hour >= 17:\n"
                "        return {'action': 'skip'}\n"
                "    return None\n"
            ),
        },
        {
            "id": "template_client_name",
            "name": "Client name detector",
            "description": "Extract and tag the client name from the message context.",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    client = context.get('client_name', '').strip()\n"
                "    sender_name = context.get('sender_name', '').strip()\n"
                "    name = client or sender_name\n"
                "    if name:\n"
                "        return {'action': 'tag',\n"
                "                'value': 'client:' + name.lower().replace(' ', '-')}\n"
                "    return None\n"
            ),
        },
        {
            "id": "template_sentiment",
            "name": "Sentiment detector",
            "description": "Basic positive/negative sentiment detection from keywords.",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    body = context.get('body', '').lower()\n"
                "    subject = context.get('subject', '').lower()\n"
                "    text = subject + ' ' + body\n"
                "    neg = ['angry', 'frustrated', 'terrible', 'worst',\n"
                "           'cancel', 'lawsuit', 'unacceptable', 'furious',\n"
                "           'disappointed', 'horrible']\n"
                "    pos = ['thank', 'great', 'awesome', 'love', 'excellent',\n"
                "           'fantastic', 'perfect', 'amazing', 'happy',\n"
                "           'impressed']\n"
                "    neg_count = sum(1 for w in neg if w in text)\n"
                "    pos_count = sum(1 for w in pos if w in text)\n"
                "    if neg_count > pos_count and neg_count >= 1:\n"
                "        return {'action': 'escalate',\n"
                "                'reason': 'Negative sentiment detected'}\n"
                "    if pos_count > neg_count and pos_count >= 2:\n"
                "        return {'action': 'tag', 'value': 'positive-sentiment'}\n"
                "    return None\n"
            ),
        },
        {
            "id": "template_duplicate",
            "name": "Duplicate detector",
            "description": "Skip if the same subject was already seen (uses tags as memory).",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    subject = context.get('subject', '').lower().strip()\n"
                "    tags = context.get('tags', [])\n"
                "    if not subject:\n"
                "        return None\n"
                "    seen_tag = 'seen:' + subject[:40].replace(' ', '-')\n"
                "    if isinstance(tags, list) and seen_tag in tags:\n"
                "        return {'action': 'skip'}\n"
                "    return {'action': 'tag', 'value': seen_tag}\n"
            ),
        },
        {
            "id": "template_summary",
            "name": "Summary generator",
            "description": "Generate a one-line summary by logging the first sentence of the body.",
            "trigger": "email",
            "code": (
                "def run(context):\n"
                "    body = context.get('body', '').strip()\n"
                "    if not body:\n"
                "        return None\n"
                "    for sep in ['. ', '! ', '? ', '\\n']:\n"
                "        idx = body.find(sep)\n"
                "        if idx != -1:\n"
                "            body = body[:idx + 1]\n"
                "            break\n"
                "    if len(body) > 120:\n"
                "        body = body[:117] + '...'\n"
                "    return {'action': 'log',\n"
                "            'message': 'Summary: ' + body}\n"
            ),
        },
    ]
