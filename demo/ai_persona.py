"""Zen Den — AI Persona / Behavior Editor

Manages the AI's personality, tone, response style, and per-client
customization.  Users configure how the AI communicates through the UI;
this module persists those settings and generates system prompts, response
templates, and self-correction analyses.

Usage:
    from ai_persona import (
        load_persona, get_global_config, update_global_config,
        build_system_prompt, render_template, analyze_response,
    )
"""

import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("zen.persona")

# ── Path helpers ──────────────────────────────────────────────

def _data_dir():
    if getattr(sys, "_MEIPASS", None):
        d = Path.home() / "Library" / "Application Support" / "ZenDen"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).parent


_PERSONA_PATH = _data_dir() / "ai_persona.json"


# ── Default configuration ────────────────────────────────────

_DEFAULT_PERSONA = {
    "global": {
        "name": "Zen Den",
        "tone": "friendly-professional",
        "response_length": "concise",
        "use_emoji": True,
        "greeting_style": "warm",
        "sign_off": "Best,\nZen Den",
        "system_prompt": (
            "You are a helpful marketing assistant called Zen Den. "
            "You help agency teams manage paid search campaigns, "
            "answer client questions, and provide performance insights."
        ),
        "forbidden_phrases": ["I don't know", "I can't help"],
        "always_include": ["Let me know if you need anything else"],
        "max_response_words": 150,
        "language": "en",
    },
    "per_client": {},
    "templates": {
        "campaign_status": "Hi {sender_name},\n\n{answer}\n\n{sign_off}",
        "budget_update": (
            "Hi {sender_name},\n\n"
            "Here's the latest on the budget:\n\n{answer}\n\n"
            "Let me know if you need the full report.\n\n{sign_off}"
        ),
        "promo_status": "Hi {sender_name},\n\n{answer}\n\n{sign_off}",
        "generic": "Hi {sender_name},\n\n{answer}\n\n{sign_off}",
        "escalation": (
            "Hi {sender_name},\n\n"
            "Great question — I'm flagging this for the team to review. "
            "You'll hear back shortly.\n\n{sign_off}"
        ),
        "out_of_scope": (
            "Hi {sender_name},\n\n"
            "Thanks for reaching out! This one's outside my wheelhouse "
            "— I've flagged it for the team.\n\n{sign_off}"
        ),
    },
    "tone_presets": {
        "friendly-professional": {
            "description": (
                "Warm but business-appropriate. Uses occasional emoji. "
                "Good default."
            ),
            "example": (
                "Hey Sarah! 👋 The Solara brand campaign is live and "
                "performing well — 3.2x ROAS this week. Let me know if "
                "you need the full breakdown!"
            ),
        },
        "formal": {
            "description": "Corporate tone. No emoji. Structured responses.",
            "example": (
                "Dear Sarah,\n\n"
                "Please find the current status of the Solara brand "
                "campaign below. The campaign is active with a return "
                "on ad spend of 3.2x for the current week."
            ),
        },
        "casual": {
            "description": (
                "Like texting a coworker. Short, punchy, emoji-heavy."
            ),
            "example": (
                "yo! 🚀 solara campaign is crushing it — 3.2x roas "
                "this week 💪 lmk if you need deets"
            ),
        },
        "minimal": {
            "description": "Shortest possible responses. Just the facts.",
            "example": "Solara brand campaign: ACTIVE. ROAS: 3.2x. Budget on track.",
        },
        "supportive": {
            "description": "Extra encouraging. Good for stressed teams.",
            "example": (
                "Great question, Sarah! 🌿 The Solara campaign is doing "
                "really well — 3.2x ROAS this week, which is above our "
                "target. You're doing an amazing job managing this. Let "
                "me know if you'd like the detailed report!"
            ),
        },
    },
}


# =========================================================================
# 1. Storage — load / save / global / per-client
# =========================================================================

def load_persona() -> dict:
    """Load persona config from disk, creating the default if missing."""
    try:
        if _PERSONA_PATH.exists():
            data = json.loads(_PERSONA_PATH.read_text(encoding="utf-8"))
            for section in ("global", "per_client", "templates", "tone_presets"):
                data.setdefault(section, _DEFAULT_PERSONA[section])
            return data
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Failed to load persona config, using defaults: %s", exc)

    save_persona(_DEFAULT_PERSONA)
    return json.loads(json.dumps(_DEFAULT_PERSONA))


def save_persona(config: dict) -> None:
    """Persist the full persona config to disk."""
    try:
        _PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PERSONA_PATH.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        log.error("Failed to save persona config: %s", exc)


def get_global_config() -> dict:
    """Return the ``global`` section of the persona config."""
    return load_persona().get("global", {})


def update_global_config(updates: dict) -> None:
    """Merge *updates* into the global config and save."""
    config = load_persona()
    config["global"].update(updates)
    save_persona(config)


def get_client_config(client_name: str) -> dict:
    """Return the effective config for *client_name*.

    Starts with a copy of the global config and overlays any
    client-specific overrides on top.
    """
    config = load_persona()
    merged = dict(config.get("global", {}))
    overrides = config.get("per_client", {}).get(client_name, {})
    merged.update(overrides)
    return merged


def update_client_config(client_name: str, updates: dict) -> None:
    """Save client-specific overrides for *client_name*."""
    config = load_persona()
    config.setdefault("per_client", {})
    config["per_client"].setdefault(client_name, {}).update(updates)
    save_persona(config)


def delete_client_config(client_name: str) -> bool:
    """Remove per-client overrides.  Returns ``True`` if the key existed."""
    config = load_persona()
    removed = config.get("per_client", {}).pop(client_name, None) is not None
    if removed:
        save_persona(config)
    return removed


# =========================================================================
# 2. Templates
# =========================================================================

def get_templates() -> dict:
    """Return all response templates."""
    return load_persona().get("templates", {})


def update_template(template_name: str, template_text: str) -> None:
    """Update an existing template by name."""
    config = load_persona()
    config.setdefault("templates", {})[template_name] = template_text
    save_persona(config)


def add_template(name: str, template_text: str) -> None:
    """Add a new template.  Overwrites if *name* already exists."""
    update_template(name, template_text)


def delete_template(name: str) -> bool:
    """Delete a template by name.  Returns ``True`` if it existed."""
    config = load_persona()
    removed = config.get("templates", {}).pop(name, None) is not None
    if removed:
        save_persona(config)
    return removed


def render_template(template_name: str, context: dict) -> str:
    """Render *template_name* with *context* variables.

    Available placeholders: ``{sender_name}``, ``{sender}``,
    ``{client_name}``, ``{answer}``, ``{sign_off}``, ``{greeting}``,
    ``{date}``, ``{time}``.

    Missing keys resolve to an empty string.
    """
    templates = get_templates()
    template_text = templates.get(template_name, templates.get("generic", "{answer}"))

    now = datetime.now(timezone.utc)
    defaults = defaultdict(
        str,
        sender_name="",
        sender="",
        client_name="",
        answer="",
        sign_off=get_global_config().get("sign_off", ""),
        greeting="Hi",
        date=now.strftime("%B %d, %Y"),
        time=now.strftime("%I:%M %p UTC"),
    )
    defaults.update(context)
    try:
        return template_text.format_map(defaults)
    except (KeyError, ValueError) as exc:
        log.warning("Template render failed for '%s': %s", template_name, exc)
        return template_text


# =========================================================================
# 3. Tone presets
# =========================================================================

def get_tone_presets() -> dict:
    """Return all available tone presets."""
    return load_persona().get("tone_presets", {})


def get_current_tone(client_name: str = None) -> dict:
    """Return the active tone preset for *client_name* (or global).

    Returns a dict with ``name``, ``description``, and ``example`` keys.
    If the configured tone doesn't match any preset the result still
    contains the tone name but with empty description / example.
    """
    if client_name:
        effective = get_client_config(client_name)
    else:
        effective = get_global_config()

    tone_key = effective.get("tone", "friendly-professional")
    presets = get_tone_presets()
    preset = presets.get(tone_key, {})

    return {
        "name": tone_key,
        "description": preset.get("description", ""),
        "example": preset.get("example", ""),
    }


# =========================================================================
# 4. System prompt generation
# =========================================================================

def build_system_prompt(client_name: str = None) -> str:
    """Generate a complete system prompt ready for the LLM API.

    Combines the base system prompt with tone instructions, length
    constraints, forbidden / required phrases, and any client-specific
    context.
    """
    effective = get_client_config(client_name) if client_name else get_global_config()
    tone = get_current_tone(client_name)

    parts: list[str] = []

    # Base identity
    base = effective.get("system_prompt", "")
    if base:
        parts.append(base)

    # Tone
    parts.append(f"\n## Tone\nUse a **{tone['name']}** tone.")
    if tone["description"]:
        parts.append(f"Description: {tone['description']}")
    if tone["example"]:
        parts.append(f"Example response:\n> {tone['example']}")

    # Emoji
    if effective.get("use_emoji"):
        parts.append("You may use emoji sparingly to keep things friendly.")
    else:
        parts.append("Do NOT use emoji in responses.")

    # Response length
    length = effective.get("response_length", "concise")
    max_words = effective.get("max_response_words")
    parts.append(f"\n## Response Length\nKeep responses **{length}**.")
    if max_words:
        parts.append(f"Aim for no more than {max_words} words per reply.")

    # Language
    lang = effective.get("language", "en")
    if lang and lang != "en":
        parts.append(f"\n## Language\nRespond in language code: {lang}.")

    # Forbidden phrases
    forbidden = effective.get("forbidden_phrases", [])
    if forbidden:
        items = ", ".join(f'"{p}"' for p in forbidden)
        parts.append(f"\n## Forbidden Phrases\nNever say: {items}.")

    # Required phrases
    always = effective.get("always_include", [])
    if always:
        items = "\n".join(f"- {p}" for p in always)
        parts.append(f"\n## Always Include\n{items}")

    # Client-specific context
    if client_name:
        ctx = effective.get("custom_context", "")
        if ctx:
            parts.append(f"\n## Client Context — {client_name}\n{ctx}")

        contacts = effective.get("key_contacts", [])
        if contacts:
            items = "\n".join(f"- {c}" for c in contacts)
            parts.append(f"\n## Key Contacts\n{items}")

        sensitive = effective.get("sensitive_topics", [])
        if sensitive:
            items = ", ".join(f'"{t}"' for t in sensitive)
            parts.append(
                f"\n## Sensitive Topics\n"
                f"Be extra careful when discussing: {items}. "
                "Keep answers factual and brief on these subjects."
            )

    return "\n".join(parts)


# =========================================================================
# 5. Behavior analysis (self-correction helper)
# =========================================================================

_WORD_RE = re.compile(r"\S+")


def analyze_response(response_text: str) -> dict:
    """Check *response_text* against persona rules.

    Returns a dict with:
        - ``word_count`` — number of words
        - ``has_forbidden`` — list of forbidden phrases found
        - ``missing_required`` — required phrases not present
        - ``tone_match`` — heuristic boolean
        - ``suggestions`` — human-readable improvement hints
    """
    cfg = get_global_config()
    text_lower = response_text.lower()
    words = _WORD_RE.findall(response_text)
    word_count = len(words)

    # Forbidden phrases
    forbidden = cfg.get("forbidden_phrases", [])
    has_forbidden = [p for p in forbidden if p.lower() in text_lower]

    # Required phrases
    always = cfg.get("always_include", [])
    missing_required = [p for p in always if p.lower() not in text_lower]

    # Word-count check
    max_words = cfg.get("max_response_words", 0)
    over_limit = max_words and word_count > max_words

    # Heuristic tone match
    tone_key = cfg.get("tone", "friendly-professional")
    tone_match = _check_tone_heuristic(tone_key, response_text, cfg)

    suggestions: list[str] = []
    if has_forbidden:
        suggestions.append(
            f"Remove forbidden phrase(s): {', '.join(has_forbidden)}"
        )
    if missing_required:
        suggestions.append(
            f"Add required phrase(s): {', '.join(missing_required)}"
        )
    if over_limit:
        suggestions.append(
            f"Response is {word_count} words — trim to ≤{max_words}."
        )
    if not tone_match:
        suggestions.append(
            f"Tone may not match '{tone_key}' preset — review wording."
        )

    return {
        "word_count": word_count,
        "has_forbidden": has_forbidden,
        "missing_required": missing_required,
        "tone_match": tone_match,
        "suggestions": suggestions,
    }


def _check_tone_heuristic(tone_key: str, text: str, cfg: dict) -> bool:
    """Lightweight heuristic check that *text* roughly matches *tone_key*."""
    has_emoji = bool(re.search(
        r"[\U0001f300-\U0001f9ff\u2600-\u26ff\u2700-\u27bf]", text,
    ))
    use_emoji = cfg.get("use_emoji", False)
    text_lower = text.lower()

    if tone_key == "formal":
        if has_emoji:
            return False
        if any(w in text_lower for w in ("yo!", "lmk", "deets", "crushing it")):
            return False
        return True

    if tone_key == "casual":
        return True

    if tone_key == "minimal":
        if len(_WORD_RE.findall(text)) > 50:
            return False
        return True

    if tone_key == "friendly-professional":
        if not use_emoji and has_emoji:
            return False
        return True

    if tone_key == "supportive":
        return True

    return True
