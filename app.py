"""
CMS Template Generator Dashboard

Streamlit app for converting localized Word documents into CMS-ready template packages.
"""

import shutil
import tempfile
import zipfile
import base64
import mimetypes
import textwrap
import copy
import html
from urllib.request import urlretrieve
from datetime import datetime
from pathlib import Path
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from config import (
    LANGUAGE_MAPPING,
    LANGUAGE_NAMES,
    LANGUAGE_TO_MARKET,
    TASK_TYPES,
    REWARD_TYPES,
    BONUS_PRODUCTS,
    SEND_CONDITIONS,
    OMS_IMAGES,
)
from word_parser import parse_documents_from_folder, ParsedDocument
from xml_generator import generate_cms_packages
from report_generator import build_report_from_session
import re
import difflib
import xml.etree.ElementTree as ET
from collections import Counter

try:
    from langdetect import detect as langdetect_detect, detect_langs as langdetect_detect_langs, LangDetectException
except ImportError:
    langdetect_detect = None
    langdetect_detect_langs = None
    LangDetectException = Exception


BETSSON_LOGO_URL = "https://www.betsson.com/wp-content/uploads/2024/09/white-newbetssonlogo-1.svg"
BETSSON_FAVICON_URL = "https://www.betsson.com/assets/favicons/favicon.ico"
BETSSON_FONTS_BASE = "https://www.betsson.com/wp-content/themes/betsson-theme/assets/fonts"


# Black SVG favicon: Betsson brand marker shape in #1F1F1F with white b
_BLACK_FAVICON_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>
  <rect width='32' height='32' rx='7' fill='#1F1F1F'/>
  <text x='16' y='25' font-family='Arial Black,Arial,sans-serif' font-size='21'
        font-weight='900' fill='white' text-anchor='middle'>b</text>
</svg>"""


def ensure_brand_assets() -> tuple[Path | None, Path | None, Path | None]:
    """Best-effort download of Betsson brand assets for local use."""
    assets_dir = Path(__file__).parent / "images" / "brand"
    assets_dir.mkdir(parents=True, exist_ok=True)

    logo_path = assets_dir / "betsson-logo.svg"
    favicon_path = assets_dir / "betsson-favicon.ico"
    black_favicon_path = assets_dir / "betsson-favicon-black.svg"

    try:
        if not logo_path.exists():
            urlretrieve(BETSSON_LOGO_URL, str(logo_path))
    except Exception:
        logo_path = None

    try:
        if not favicon_path.exists():
            urlretrieve(BETSSON_FAVICON_URL, str(favicon_path))
    except Exception:
        favicon_path = None

    if not black_favicon_path.exists():
        black_favicon_path.write_text(_BLACK_FAVICON_SVG, encoding="utf-8")

    return logo_path, favicon_path, black_favicon_path


ENGLISH_HINT_WORDS = {
    "the", "and", "for", "with", "your", "you", "when", "place", "placing", "claim",
    "offer", "free", "cash", "spins", "sportsbook", "chance", "perfect", "try", "get",
}


def generate_language_mismatch_report(parsed_docs: list[ParsedDocument]) -> dict:
    """
    Detect if document content language matches expected language from filename.
    
    Uses langdetect to sample actual content and compare against the expected
    language_code from the filename. Treats detection as a heuristic hint —
    short text and similar language pairs (ES/PT, NB/SV) may cause false positives.
    
    Args:
        parsed_docs: List of ParsedDocument objects with language_code and content fields
        
    Returns:
        Dict keyed by language_code with mismatch detection results.
        Example: {
            "EN": {"detected_language": "en", "mismatch": False},
            "ES": {"detected_language": "en", "mismatch": True}
        }
    """
    if langdetect_detect is None:
        return {doc.language_code: {"detected_language": None, "mismatch": False} for doc in parsed_docs}

    def normalize_expected_lang(code: str) -> str:
        """Normalize language/market/CMS codes to base langdetect-compatible language codes."""
        code = (code or "").lower().strip()
        if not code:
            return code

        # Handle cms variants like es-ar-ba, ru-ee, en-pe
        if "-" in code:
            return code.split("-", 1)[0]

        # Market codes that represent Spanish/Portuguese content
        if code in {"arg", "cl", "co", "mx", "pe", "py"}:
            return "es"
        if code == "br":
            return "pt"

        # Workspace-specific aliases
        aliases = {
            "gr": "el",  # Greek
            "no": "no",  # Norwegian
        }
        return aliases.get(code, code)

    def expand_tolerated_langs(expected_langs: set[str]) -> set[str]:
        """Allow close language families that langdetect commonly confuses."""
        tolerated = set(expected_langs)
        if "is" in expected_langs:
            tolerated.update({"no", "da", "sv"})
        if "no" in expected_langs:
            tolerated.update({"da", "sv"})
        return tolerated

    def clean_sample(text: str) -> str:
        text = re.sub(r"\{[^}]+\}", " ", text)
        text = re.sub(r"%%[^%]*%%", " ", text)
        text = re.sub(r"https?://\S+|www\.\S+", " ", text)
        text = re.sub(r"[^A-Za-z\u00C0-\u024F\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def clean_for_detection(text: str) -> str:
        """Strip placeholders and URLs but preserve all Unicode chars for accurate langdetect."""
        text = re.sub(r"\{[^}]+\}", " ", text)
        text = re.sub(r"%%[^%]*%%", " ", text)
        text = re.sub(r"https?://\S+|www\.\S+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def is_structural_chunk(text: str) -> bool:
        """Skip section labels/headers that are not representative language content."""
        upper = text.upper().strip()
        if not upper:
            return True
        structural_keywords = [
            "MY OFFERS", "LAUNCH", "REMINDER", "OMS", "SMS", "TEMPLATE", "TITLE",
            "BODY", "CTA", "TASK", "REWARD", "TERMS", "CONDITIONS", "VARIANT",
        ]
        return len(upper.split()) <= 6 and any(keyword in upper for keyword in structural_keywords)

    def evaluate_chunk(text: str, expected_langs: set[str]) -> dict:
        cleaned = clean_sample(text)
        detection_text = clean_for_detection(text)
        latin_tokens = [token.lower() for token in cleaned.split() if len(token) > 2]
        all_tokens = [token.lower() for token in detection_text.split() if len(token) > 2]
        english_hits = sum(1 for token in latin_tokens if token in ENGLISH_HINT_WORDS)
        english_ratio = english_hits / max(len(latin_tokens), 1)

        if not all_tokens or len(all_tokens) < 12:
            if "en" not in expected_langs and english_hits >= 6 and english_ratio >= 0.55:
                return {
                    "detected_language": "en",
                    "mismatch": True,
                    "reason": "english_hint_short_sample",
                    "sample_length": len(detection_text),
                    "english_probability": 0.0,
                    "detected_probability": 0.0,
                    "english_hint_ratio": round(english_ratio, 4),
                }
            return {
                "detected_language": None,
                "mismatch": False,
                "reason": "insufficient_sample",
                "sample_length": len(detection_text),
                "english_probability": 0.0,
                "detected_probability": 0.0,
                "english_hint_ratio": round(english_ratio, 4),
            }

        try:
            text_for_detection = detection_text[:3000]
            detected_lang = langdetect_detect(text_for_detection).lower()[:2]

            lang_probabilities = {}
            if langdetect_detect_langs is not None:
                try:
                    lang_probabilities = {
                        candidate.lang.lower()[:2]: float(candidate.prob)
                        for candidate in langdetect_detect_langs(text_for_detection)
                    }
                except Exception:
                    lang_probabilities = {}

            english_prob = lang_probabilities.get("en", 0.0)
            detected_prob = lang_probabilities.get(detected_lang, 0.0)
            mismatch = (
                detected_lang not in expected_langs
                and detected_prob >= 0.8
                and len(all_tokens) >= 20
            )

            if "en" not in expected_langs and english_prob >= 0.85 and english_ratio >= 0.28 and len(all_tokens) >= 20:
                mismatch = True
                detected_lang = "en"
                detected_prob = english_prob

            return {
                "detected_language": detected_lang,
                "mismatch": mismatch,
                "reason": "chunk_eval",
                "sample_length": len(detection_text),
                "english_probability": round(english_prob, 4),
                "detected_probability": round(detected_prob, 4),
                "english_hint_ratio": round(english_ratio, 4),
            }
        except LangDetectException:
            return {
                "detected_language": None,
                "mismatch": False,
                "reason": "detection_failed",
                "sample_length": len(detection_text),
                "english_probability": 0.0,
                "detected_probability": 0.0,
                "english_hint_ratio": round(english_ratio, 4),
            }

    def select_better_result(existing: dict | None, candidate: dict) -> dict:
        """Pick the more useful detection result for the same language across multiple docs."""
        if not existing:
            return candidate

        existing_mismatch = bool(existing.get("mismatch"))
        candidate_mismatch = bool(candidate.get("mismatch"))

        # Always prefer a mismatch if one doc has it and another does not.
        if candidate_mismatch and not existing_mismatch:
            return candidate
        if existing_mismatch and not candidate_mismatch:
            return existing

        # If both are mismatches, keep the stronger signal.
        if candidate_mismatch and existing_mismatch:
            candidate_score = (
                float(candidate.get("english_probability", 0.0)),
                float(candidate.get("detected_probability", 0.0)),
                int(candidate.get("sample_length", 0)),
            )
            existing_score = (
                float(existing.get("english_probability", 0.0)),
                float(existing.get("detected_probability", 0.0)),
                int(existing.get("sample_length", 0)),
            )
            return candidate if candidate_score >= existing_score else existing

        # Neither is mismatch: keep the richer sample.
        candidate_score = (
            int(candidate.get("sample_length", 0)),
            float(candidate.get("detected_probability", 0.0)),
        )
        existing_score = (
            int(existing.get("sample_length", 0)),
            float(existing.get("detected_probability", 0.0)),
        )
        return candidate if candidate_score >= existing_score else existing

    results = {}

    for doc in parsed_docs:
        language_code = doc.language_code

        expected_langs = set()
        mapping_codes = LANGUAGE_MAPPING.get(language_code.upper(), [])
        if mapping_codes:
            expected_langs.update(normalize_expected_lang(code) for code in mapping_codes)
        else:
            expected_langs.add(normalize_expected_lang(language_code))
        tolerated_langs = expand_tolerated_langs(expected_langs)

        content_chunks: list[str] = []

        for section in [doc.launch_oms, doc.reminder_oms, doc.reward_oms]:
            if section and hasattr(section, "templates"):
                for template in section.templates:
                    chunk = " ".join(part for part in [template.title, template.body, template.cta, template.cta_mobile] if part)
                    if chunk and not is_structural_chunk(chunk):
                        content_chunks.append(chunk)

        for section in [doc.launch_sms, doc.reminder_sms]:
            if section and hasattr(section, "templates"):
                for template in section.templates:
                    if template.body:
                        if not is_structural_chunk(template.body):
                            content_chunks.append(template.body)

        # Fallback to raw paragraphs only when section parsing found no usable chunks.
        if not content_chunks and getattr(doc, "raw_paragraphs", None):
            for para in doc.raw_paragraphs:
                if para and para.strip() and not is_structural_chunk(para):
                    content_chunks.append(para)

        chunk_results = [evaluate_chunk(chunk, tolerated_langs) for chunk in content_chunks if chunk and chunk.strip()]
        mismatches = [item for item in chunk_results if item.get("mismatch")]

        if mismatches:
            winner = max(
                mismatches,
                key=lambda item: (
                    item.get("english_probability", 0.0),
                    item.get("detected_probability", 0.0),
                    item.get("sample_length", 0),
                ),
            )
            winner = {**winner, "reason": "chunk_mismatch"}
            results[language_code] = select_better_result(results.get(language_code), winner)
            continue

        if chunk_results:
            best_non_mismatch = max(chunk_results, key=lambda item: item.get("sample_length", 0))
            results[language_code] = select_better_result(results.get(language_code), best_non_mismatch)
            continue

        no_content_result = {
            "detected_language": None,
            "mismatch": False,
            "reason": "no_content",
            "sample_length": 0,
            "english_probability": 0.0,
            "detected_probability": 0.0,
            "english_hint_ratio": 0.0,
        }
        results[language_code] = select_better_result(results.get(language_code), no_content_result)

    return results


# =============================================================================
# VALIDATION HELPERS
# =============================================================================

# Valid CW placeholders (extracted from personalized-promotions-admin codebase)
# See: Knowledge_Base/Reference/Campaign Wizard - Placeholders Reference.md
VALID_PLACEHOLDERS = {
    # Common
    "BrandName", "BrandDomain", "PalantirDomain", "OfferId",
    "CampaignEndDateAndTime", "LastContentChangeLocalTimeStamp",
    
    # Customer
    "CustomerFirstName", "CustomerLastName", "CustomerGuid", "CustomerTotalBalance",
    
    # Deposit Task
    "DepositFulfillmentAmount", "DepositExcludedPayments",
    
    # Wager Task (Casino)
    "WagerTaskAmount", "WagerTaskOn",
    
    # Place Bet Task (Sportsbook)
    "SBWagerTaskOn", "TaskMinimumOdds", "TaskMinimumSelections",
    "TaskIncludedBetTypes", "TaskIncludedBettingMarkets",
    
    # Net Loss Gameplay (Cashback)
    "NetLossGameplayTaskOn", "NetLossGameplayPercentage",
    "NetLossGameplayMinimumAmount", "NetLossGameplayMaxReceivedAmount",
    "NetLossGameplayMinimumGameRounds", "NetLossGameplayMinimumStakeRound",
    
    # Net Loss Sportsbook
    "NetLossSportsbookTaskOn", "NetLossSportsbookPercentage",
    "NetLossSportsbookMinimumAmount", "NetLossSportsbookMaxReceivedAmount",
    "NetLossSportsbookMinimumWager", "NetLossSportsbookMinimumOdds",
    "NetLossSportsbookBetType",
    
    # Free Spins Reward
    "NrOfFreespins", "FreespinGames", "FreespinValidityDays",
    "FreespinValue", "WinningsLifetime", "WageringRequirementMultiplier",
    "FreespinValidityHours",
    
    # Bonus Money Reward
    "BonusAmount", "BonusLifetime", "BonusDescription",
    
    # Cash Reward
    "CashRewardAmount",
    
    # Sportsbook Rewards (Free Bet)
    "SBRewardStake", "SBRewardMinSelections", "SBRewardClaimableDuration", "SBRewardOn",
}

def get_sms_char_info(text: str) -> tuple[int, str, str]:
    """
    Get SMS character count info.
    Returns: (char_count, status_color, status_message)
    
    SMS limits:
    - 1 SMS: 160 chars (GSM-7) or 70 (Unicode)
    - 2 SMS: 306 chars (GSM-7) or 134 (Unicode)
    - 3 SMS: 459 chars (GSM-7) or 201 (Unicode)
    """
    if not text:
        return 0, "gray", "Empty"
    
    char_count = len(text)
    
    # Simple GSM-7 check (placeholders will be replaced, so be conservative)
    if char_count <= 160:
        return char_count, "green", f"✅ {char_count}/160 (1 SMS)"
    elif char_count <= 306:
        return char_count, "orange", f"⚠️ {char_count}/306 (2 SMS)"
    elif char_count <= 459:
        return char_count, "orange", f"⚠️ {char_count}/459 (3 SMS)"
    else:
        return char_count, "red", f"❌ {char_count} chars - TOO LONG!"


def validate_placeholders(text: str) -> list[str]:
    """
    Find invalid placeholders in text.
    Returns list of invalid placeholder names.
    """
    if not text:
        return []
    
    # Find all %%xyz%% patterns
    pattern = r'%%([A-Za-z0-9_]+)%%'
    found = re.findall(pattern, text)
    
    invalid = [p for p in found if p not in VALID_PLACEHOLDERS]
    return invalid


def _split_placeholder_words(token: str) -> list[str]:
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", token)
    return [p.lower() for p in parts if p]


def _score_placeholder_candidate(token: str, candidate: str) -> float:
    token_lower = token.lower()
    cand_lower = candidate.lower()
    ratio = difflib.SequenceMatcher(None, token_lower, cand_lower).ratio()
    token_words = set(_split_placeholder_words(token))
    cand_words = set(_split_placeholder_words(candidate))
    overlap = (len(token_words & cand_words) / max(1, len(token_words))) if token_words else 0.0
    return ratio + (0.25 * overlap)


def _confidence_from_score(score: float) -> str:
    if score >= 0.93:
        return "high"
    if score >= 0.83:
        return "medium"
    return "low"


def get_placeholder_replacement_plan(text: str, max_suggestions: int = 3) -> dict[str, dict]:
    """Return replacement plan per invalid token with candidates and confidence tier."""
    invalid_tokens = sorted(set(validate_placeholders(text)))
    plan: dict[str, dict] = {}
    canonical_by_lower = {p.lower(): p for p in VALID_PLACEHOLDERS}
    valid_sorted = sorted(VALID_PLACEHOLDERS)

    for token in invalid_tokens:
        token_lower = token.lower()

        # Same token with only casing difference is always safe.
        if token_lower in canonical_by_lower:
            canonical = canonical_by_lower[token_lower]
            plan[token] = {
                "candidates": [canonical],
                "best": canonical,
                "score": 1.0,
                "confidence": "high",
            }
            continue

        scored: list[tuple[float, str]] = []
        for candidate in valid_sorted:
            score = _score_placeholder_candidate(token, candidate)
            ratio = difflib.SequenceMatcher(None, token_lower, candidate.lower()).ratio()
            token_words = set(_split_placeholder_words(token))
            cand_words = set(_split_placeholder_words(candidate))
            overlap = (len(token_words & cand_words) / max(1, len(token_words))) if token_words else 0.0

            if ratio < 0.68:
                continue
            if overlap == 0 and ratio < 0.82:
                continue

            scored.append((score, candidate))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_candidates = [candidate for _, candidate in scored[:max_suggestions]]

        if top_candidates:
            top_score = scored[0][0]
            plan[token] = {
                "candidates": top_candidates,
                "best": top_candidates[0],
                "score": top_score,
                "confidence": _confidence_from_score(top_score),
            }
        else:
            plan[token] = {
                "candidates": [],
                "best": None,
                "score": 0.0,
                "confidence": "low",
            }

    return plan


def suggest_placeholder_corrections(text: str, max_suggestions: int = 3) -> dict[str, list[str]]:
    """Backward-compatible simple suggestion mapping for invalid tokens."""
    plan = get_placeholder_replacement_plan(text=text, max_suggestions=max_suggestions)
    return {token: details["candidates"] for token, details in plan.items()}


def get_safe_placeholder_replacements(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return only high-confidence replacements and token confidence map."""
    plan = get_placeholder_replacement_plan(text)
    replacements: dict[str, str] = {}
    confidence_map: dict[str, str] = {}

    for token, details in plan.items():
        confidence = details["confidence"]
        confidence_map[token] = confidence
        if confidence == "high" and details["best"]:
            replacements[token] = details["best"]

    return replacements, confidence_map


def render_suggestion_hints(field_label: str, suggestions: dict[str, list[str]]) -> None:
    """Render concise inline typo hints for invalid placeholders."""
    for wrong_token, candidates in suggestions.items():
        if candidates:
            best = f"%%{candidates[0]}%%"
            if len(candidates) > 1:
                alternatives = ", ".join([f"%%{c}%%" for c in candidates[1:]])
                st.caption(f"💡 {field_label}: `%%{wrong_token}%%` -> try `{best}` (alternatives: {alternatives})")
            else:
                st.caption(f"💡 {field_label}: `%%{wrong_token}%%` -> try `{best}`")
        else:
            st.caption(f"💡 {field_label}: no close match found for `%%{wrong_token}%%`")


def apply_placeholder_replacements(text: str, replacements: dict[str, str]) -> str:
    """Apply placeholder token replacements like %%Wrong%% -> %%Right%% to a text block."""
    updated = text or ""
    for wrong_token, right_token in replacements.items():
        updated = updated.replace(f"%%{wrong_token}%%", f"%%{right_token}%%")
    return updated


def collect_resolved_status_transitions(previous: dict[str, str], current: dict[str, str]) -> list[str]:
    """Collect language statuses that transitioned from issue state to ready."""
    resolved: list[str] = []
    for lang, current_state in current.items():
        prev_state = previous.get(lang)
        if prev_state in {"missing", "invalid"} and current_state == "ready":
            resolved.append(f"{lang} ({prev_state} -> ready)")
    return resolved


def track_fix_applied(language_code: str, field_label: str, replacements: dict[str, str]) -> None:
    """Persist fix metrics and replacement details in session state for audit reporting."""
    replacements_count = len(replacements or {})
    if replacements_count <= 0:
        return

    if "qa_fixes_applied" not in st.session_state:
        st.session_state["qa_fixes_applied"] = {}
    if "qa_fix_details" not in st.session_state:
        st.session_state["qa_fix_details"] = {}
    if "qa_fix_events" not in st.session_state:
        st.session_state["qa_fix_events"] = []

    per_language = st.session_state["qa_fixes_applied"].setdefault(language_code, {})
    per_language[field_label] = per_language.get(field_label, 0) + replacements_count

    details_by_language = st.session_state["qa_fix_details"].setdefault(language_code, {})
    detail_list = details_by_language.setdefault(field_label, [])
    for wrong_token, right_token in replacements.items():
        pair = f"%%{wrong_token}%%→%%{right_token}%%"
        if pair not in detail_list:
            detail_list.append(pair)

    st.session_state["qa_fix_events"].append(
        {
            "language": language_code,
            "field": field_label,
            "replacements": [f"%%{w}%%→%%{r}%%" for w, r in replacements.items()],
            "count": replacements_count,
        }
    )


def track_content_edit_event(language_code: str, field_label: str, before_text: str, after_text: str, source: str) -> None:
    """Track explicit edit events (auto-fix/manual-fix actions) to ensure audit completeness."""
    if (before_text or "") == (after_text or ""):
        return

    if "qa_content_edit_events" not in st.session_state:
        st.session_state["qa_content_edit_events"] = []

    old_val = before_text or ""
    new_val = after_text or ""
    old_invalid = len(validate_placeholders(old_val))
    new_invalid = len(validate_placeholders(new_val))
    before_tokens = re.findall(r'%%([A-Za-z0-9_]+)%%', old_val)
    after_tokens = re.findall(r'%%([A-Za-z0-9_]+)%%', new_val)
    before_counter = Counter(before_tokens)
    after_counter = Counter(after_tokens)
    token_delta = 0
    for token in set(before_counter.keys()) | set(after_counter.keys()):
        token_delta += abs(before_counter.get(token, 0) - after_counter.get(token, 0))

    event = {
        "language": language_code,
        "field": field_label,
        "before": old_val,
        "after": new_val,
        "invalid_before": old_invalid,
        "invalid_after": new_invalid,
        "resolved_invalid_placeholders": max(0, old_invalid - new_invalid),
        "added_invalid_placeholders": max(0, new_invalid - old_invalid),
        "placeholder_token_delta": token_delta,
        "source": source,
    }

    signature = f"{language_code}|{field_label}|{old_val}|{new_val}|{source}"
    existing_signatures = {
        f"{e.get('language','')}|{e.get('field','')}|{e.get('before','')}|{e.get('after','')}|{e.get('source','')}"
        for e in st.session_state["qa_content_edit_events"]
    }
    if signature not in existing_signatures:
        st.session_state["qa_content_edit_events"].append(event)


def collect_content_edit_log(original_docs: list[ParsedDocument], current_docs: list[ParsedDocument]) -> list[dict]:
    """Collect structured log of in-app content edits for audit report."""

    def normalize(value: str | None) -> str:
        return (value or "").strip()

    def append_if_changed(logs: list[dict], lang: str, field: str, before: str | None, after: str | None) -> None:
        old_val = normalize(before)
        new_val = normalize(after)
        if old_val == new_val:
            return
        old_invalid = len(validate_placeholders(old_val))
        new_invalid = len(validate_placeholders(new_val))
        before_tokens = re.findall(r'%%([A-Za-z0-9_]+)%%', old_val)
        after_tokens = re.findall(r'%%([A-Za-z0-9_]+)%%', new_val)
        before_counter = Counter(before_tokens)
        after_counter = Counter(after_tokens)
        token_delta = 0
        for token in set(before_counter.keys()) | set(after_counter.keys()):
            token_delta += abs(before_counter.get(token, 0) - after_counter.get(token, 0))
        logs.append(
            {
                "language": lang,
                "field": field,
                "before": old_val,
                "after": new_val,
                "invalid_before": old_invalid,
                "invalid_after": new_invalid,
                "resolved_invalid_placeholders": max(0, old_invalid - new_invalid),
                "added_invalid_placeholders": max(0, new_invalid - old_invalid),
                "placeholder_token_delta": token_delta,
            }
        )

    original_by_lang = {d.language_code: d for d in original_docs}
    logs: list[dict] = []

    for current in current_docs:
        lang = current.language_code
        original = original_by_lang.get(lang)
        if not original:
            continue

        if original.launch_sms and current.launch_sms:
            for idx, tmpl in enumerate(current.launch_sms.templates):
                old = original.launch_sms.templates[idx].body if idx < len(original.launch_sms.templates) else ""
                append_if_changed(logs, lang, f"SMS Launch {tmpl.variant} Body", old, tmpl.body)

        if original.reminder_sms and current.reminder_sms:
            for idx, tmpl in enumerate(current.reminder_sms.templates):
                old = original.reminder_sms.templates[idx].body if idx < len(original.reminder_sms.templates) else ""
                append_if_changed(logs, lang, f"SMS Reminder {tmpl.variant} Body", old, tmpl.body)

        if original.launch_oms and current.launch_oms:
            for idx, tmpl in enumerate(current.launch_oms.templates):
                old_t = original.launch_oms.templates[idx] if idx < len(original.launch_oms.templates) else None
                append_if_changed(logs, lang, f"OMS Launch {tmpl.variant} Title", old_t.title if old_t else "", tmpl.title)
                append_if_changed(logs, lang, f"OMS Launch {tmpl.variant} Body", old_t.body if old_t else "", tmpl.body)
                append_if_changed(logs, lang, f"OMS Launch {tmpl.variant} CTA", old_t.cta if old_t else "", tmpl.cta)

        if original.reminder_oms and current.reminder_oms:
            for idx, tmpl in enumerate(current.reminder_oms.templates):
                old_t = original.reminder_oms.templates[idx] if idx < len(original.reminder_oms.templates) else None
                append_if_changed(logs, lang, f"OMS Reminder {tmpl.variant} Title", old_t.title if old_t else "", tmpl.title)
                append_if_changed(logs, lang, f"OMS Reminder {tmpl.variant} Body", old_t.body if old_t else "", tmpl.body)
                append_if_changed(logs, lang, f"OMS Reminder {tmpl.variant} CTA", old_t.cta if old_t else "", tmpl.cta)

        if original.reward_oms and current.reward_oms:
            for idx, tmpl in enumerate(current.reward_oms.templates):
                old_t = original.reward_oms.templates[idx] if idx < len(original.reward_oms.templates) else None
                append_if_changed(logs, lang, f"OMS Claimed Reward {tmpl.variant} Title", old_t.title if old_t else "", tmpl.title)
                append_if_changed(logs, lang, f"OMS Claimed Reward {tmpl.variant} Body", old_t.body if old_t else "", tmpl.body)
                append_if_changed(logs, lang, f"OMS Claimed Reward {tmpl.variant} CTA", old_t.cta if old_t else "", tmpl.cta)

        if original.tc and current.tc:
            append_if_changed(logs, lang, "T&C Significant Terms", original.tc.significant_terms, current.tc.significant_terms)
            append_if_changed(logs, lang, "T&C Full Terms", original.tc.terms_and_conditions, current.tc.terms_and_conditions)

    return logs


def filter_auto_fix_only_edits(
    content_edits: list[dict],
    fix_details: dict[str, dict[str, list[str]]],
) -> list[dict]:
    """Remove edits that are completely explained by tracked auto-fix replacements."""

    def parse_replacements(replacement_pairs: list[str]) -> dict[str, str]:
        replacements: dict[str, str] = {}
        for pair in replacement_pairs or []:
            if "%%→%%" not in pair:
                continue
            left, right = pair.split("→", 1)
            wrong_token = left.replace("%%", "").strip()
            right_token = right.replace("%%", "").strip()
            if wrong_token and right_token:
                replacements[wrong_token] = right_token
        return replacements

    filtered: list[dict] = []
    for edit in content_edits:
        language = edit.get("language", "")
        field = edit.get("field", "")
        replacement_pairs = fix_details.get(language, {}).get(field, [])
        replacements = parse_replacements(replacement_pairs)

        if not replacements:
            filtered.append(edit)
            continue

        before = edit.get("before", "") or ""
        after = edit.get("after", "") or ""
        expected_after = apply_placeholder_replacements(before, replacements)
        if expected_after.strip() == after.strip():
            continue

        filtered.append(edit)

    return filtered


def choose_next_issue_language(current_lang: str, issue_langs: list[str]) -> str | None:
    """Choose next issue language relative to current language."""
    if not issue_langs:
        return None
    if current_lang not in issue_langs:
        return issue_langs[0]
    idx = issue_langs.index(current_lang)
    return issue_langs[(idx + 1) % len(issue_langs)]


def apply_safe_fixes_for_language(selected_lang: str, selected_doc: ParsedDocument) -> list[str]:
    """Apply high-confidence placeholder fixes for all editable fields in one language."""
    changes: list[str] = []

    def apply_on_widget_key(widget_key: str, fallback_text: str, label: str) -> None:
        current_text = get_effective_widget_value(widget_key, fallback_text)
        replacements, _ = get_safe_placeholder_replacements(current_text)
        if not replacements:
            return

        updated_text = apply_placeholder_replacements(current_text, replacements)
        if updated_text == current_text:
            return

        fix_buffer_key = f"fix_buffer_{widget_key}"
        undo_key = f"undo_{fix_buffer_key}"
        undo_stack = st.session_state.get(undo_key, [])
        undo_stack.append(current_text)
        st.session_state[undo_key] = undo_stack[-5:]
        st.session_state[widget_key] = updated_text
        set_editor_value(widget_key, updated_text)
        track_content_edit_event(selected_lang, label, current_text, updated_text, "auto-fix")

        replacement_pairs = [f"%%{wrong}%%→%%{right}%%" for wrong, right in replacements.items()]
        if len(replacement_pairs) > 2:
            pair_summary = ", ".join(replacement_pairs[:2]) + f" (+{len(replacement_pairs) - 2} more)"
        else:
            pair_summary = ", ".join(replacement_pairs)
        changes.append(f"{label}: {pair_summary}")
        track_fix_applied(selected_lang, label, replacements)

    sms_idx = 0
    if selected_doc.launch_sms:
        for template in selected_doc.launch_sms.templates:
            key = f"sms_{selected_lang}_{sms_idx}_Launch_{template.variant}"
            apply_on_widget_key(key, template.body or "", f"SMS Launch {template.variant}")
            sms_idx += 1
    if selected_doc.reminder_sms:
        for template in selected_doc.reminder_sms.templates:
            key = f"sms_{selected_lang}_{sms_idx}_Reminder_{template.variant}"
            apply_on_widget_key(key, template.body or "", f"SMS Reminder {template.variant}")
            sms_idx += 1

    oms_idx = 0
    if selected_doc.launch_oms:
        for template in selected_doc.launch_oms.templates:
            apply_on_widget_key(
                f"oms_title_{selected_lang}_{oms_idx}_Launch_{template.variant}",
                template.title or "",
                f"OMS Launch {template.variant} Title",
            )
            apply_on_widget_key(
                f"oms_body_{selected_lang}_{oms_idx}_Launch_{template.variant}",
                template.body or "",
                f"OMS Launch {template.variant} Body",
            )
            apply_on_widget_key(
                f"oms_cta_{selected_lang}_{oms_idx}_Launch_{template.variant}",
                template.cta or "",
                f"OMS Launch {template.variant} CTA",
            )
            oms_idx += 1
    if selected_doc.reminder_oms:
        for template in selected_doc.reminder_oms.templates:
            apply_on_widget_key(
                f"oms_title_{selected_lang}_{oms_idx}_Reminder_{template.variant}",
                template.title or "",
                f"OMS Reminder {template.variant} Title",
            )
            apply_on_widget_key(
                f"oms_body_{selected_lang}_{oms_idx}_Reminder_{template.variant}",
                template.body or "",
                f"OMS Reminder {template.variant} Body",
            )
            apply_on_widget_key(
                f"oms_cta_{selected_lang}_{oms_idx}_Reminder_{template.variant}",
                template.cta or "",
                f"OMS Reminder {template.variant} CTA",
            )
            oms_idx += 1
    if selected_doc.reward_oms:
        for template in selected_doc.reward_oms.templates:
            apply_on_widget_key(
                f"oms_title_{selected_lang}_{oms_idx}_Reward_{template.variant}",
                template.title or "",
                f"OMS Claimed Reward {template.variant} Title",
            )
            apply_on_widget_key(
                f"oms_body_{selected_lang}_{oms_idx}_Reward_{template.variant}",
                template.body or "",
                f"OMS Claimed Reward {template.variant} Body",
            )
            apply_on_widget_key(
                f"oms_cta_{selected_lang}_{oms_idx}_Reward_{template.variant}",
                template.cta or "",
                f"OMS Claimed Reward {template.variant} CTA",
            )
            oms_idx += 1

    if selected_doc.tc:
        apply_on_widget_key(
            f"tc_sig_{selected_lang}",
            selected_doc.tc.significant_terms or "",
            "T&C Significant Terms",
        )
        apply_on_widget_key(
            f"tc_full_{selected_lang}",
            selected_doc.tc.terms_and_conditions or "",
            "T&C Full Terms",
        )

    return changes


def count_safe_fixes_for_language(selected_lang: str, selected_doc: ParsedDocument) -> int:
    """Return how many field-level safe fixes are currently available for a language."""
    fixable_fields = 0

    def count_on_widget_key(widget_key: str, fallback_text: str) -> None:
        nonlocal fixable_fields
        fix_buffer_key = f"fix_buffer_{widget_key}"
        current_text = st.session_state.get(fix_buffer_key, st.session_state.get(widget_key, fallback_text or ""))
        replacements, _ = get_safe_placeholder_replacements(current_text)
        if not replacements:
            return
        updated_text = apply_placeholder_replacements(current_text, replacements)
        if updated_text != current_text:
            fixable_fields += 1

    sms_idx = 0
    if selected_doc.launch_sms:
        for template in selected_doc.launch_sms.templates:
            key = f"sms_{selected_lang}_{sms_idx}_Launch_{template.variant}"
            count_on_widget_key(key, template.body or "")
            sms_idx += 1
    if selected_doc.reminder_sms:
        for template in selected_doc.reminder_sms.templates:
            key = f"sms_{selected_lang}_{sms_idx}_Reminder_{template.variant}"
            count_on_widget_key(key, template.body or "")
            sms_idx += 1

    oms_idx = 0
    if selected_doc.launch_oms:
        for template in selected_doc.launch_oms.templates:
            count_on_widget_key(f"oms_title_{selected_lang}_{oms_idx}_Launch_{template.variant}", template.title or "")
            count_on_widget_key(f"oms_body_{selected_lang}_{oms_idx}_Launch_{template.variant}", template.body or "")
            count_on_widget_key(f"oms_cta_{selected_lang}_{oms_idx}_Launch_{template.variant}", template.cta or "")
            oms_idx += 1
    if selected_doc.reminder_oms:
        for template in selected_doc.reminder_oms.templates:
            count_on_widget_key(f"oms_title_{selected_lang}_{oms_idx}_Reminder_{template.variant}", template.title or "")
            count_on_widget_key(f"oms_body_{selected_lang}_{oms_idx}_Reminder_{template.variant}", template.body or "")
            count_on_widget_key(f"oms_cta_{selected_lang}_{oms_idx}_Reminder_{template.variant}", template.cta or "")
            oms_idx += 1
    if selected_doc.reward_oms:
        for template in selected_doc.reward_oms.templates:
            count_on_widget_key(f"oms_title_{selected_lang}_{oms_idx}_Reward_{template.variant}", template.title or "")
            count_on_widget_key(f"oms_body_{selected_lang}_{oms_idx}_Reward_{template.variant}", template.body or "")
            count_on_widget_key(f"oms_cta_{selected_lang}_{oms_idx}_Reward_{template.variant}", template.cta or "")
            oms_idx += 1

    if selected_doc.tc:
        count_on_widget_key(f"tc_sig_{selected_lang}", selected_doc.tc.significant_terms or "")
        count_on_widget_key(f"tc_full_{selected_lang}", selected_doc.tc.terms_and_conditions or "")

    return fixable_fields


def render_invalid_placeholder_assistant(
    field_label: str,
    text: str,
    fix_buffer_key: str,
    button_key: str,
    language_code: str,
    tracking_field_label: str,
) -> None:
    """Render compact invalid placeholder warning with confidence-aware fix/undo."""
    invalid = validate_placeholders(text)
    if not invalid:
        return

    invalid_labels = ", ".join([f"%%{p}%%" for p in invalid])
    plan = get_placeholder_replacement_plan(text)
    replacements, confidence_map = get_safe_placeholder_replacements(text)
    suggestions = {token: details["candidates"] for token, details in plan.items()}
    undo_key = f"undo_{fix_buffer_key}"
    undo_stack = st.session_state.get(undo_key, [])

    col_msg, col_actions = st.columns([7, 2])
    with col_msg:
        st.markdown(
            (
                "<div style='"
                "padding:7px 10px;"
                "border-radius:8px;"
                "background:#4a2229;"
                "border:1px solid #7a3641;"
                "color:#ffd9de;"
                "font-size:0.92rem;"
                "margin:2px 0 2px 0;"
                "'>"
                f"✖ {field_label}: invalid placeholders {invalid_labels}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

    with col_actions:
        has_fixes = len(replacements) > 0
        if len(replacements) == 1:
            apply_label = "Fix safe"
        else:
            apply_label = f"Fix safe ({len(replacements)})"
        if st.button(
            apply_label,
            key=button_key,
            type="primary",
            width="stretch",
            disabled=not has_fixes,
            help="Apply only high-confidence placeholder correction(s) for this field.",
        ):
            undo_stack.append(text)
            st.session_state[undo_key] = undo_stack[-5:]
            fixed_content = apply_placeholder_replacements(text, replacements)
            st.session_state[fix_buffer_key] = fixed_content
            track_fix_applied(language_code, tracking_field_label, replacements)
            track_content_edit_event(language_code, tracking_field_label, text, fixed_content, "auto-fix")
            st.session_state["qa_advance_after_fix"] = True
            st.rerun()

        if st.button(
            "Undo",
            key=f"undo_btn_{button_key}",
            type="secondary",
            width="stretch",
            disabled=len(undo_stack) == 0,
            help="Restore previous value for this field.",
        ):
            previous_text = undo_stack.pop()
            st.session_state[undo_key] = undo_stack
            st.session_state[fix_buffer_key] = previous_text
            st.rerun()

    high_tokens = [f"%%{t}%%→%%{plan[t]['best']}%%" for t in plan if confidence_map.get(t) == "high" and plan[t]["best"]]
    medium_tokens = [f"%%{t}%%→%%{plan[t]['best']}%%" for t in plan if confidence_map.get(t) == "medium" and plan[t]["best"]]
    low_tokens = [f"%%{t}%%" for t in plan if confidence_map.get(t) == "low"]

    summary_parts = []
    if high_tokens:
        summary_parts.append("H: " + ", ".join(high_tokens))
    if medium_tokens:
        summary_parts.append("M: " + ", ".join(medium_tokens))
    if low_tokens:
        summary_parts.append("L: " + ", ".join(low_tokens))

    if summary_parts:
        st.caption("💡 " + " | ".join(summary_parts))

    if not replacements and suggestions:
        st.caption("No high-confidence auto-fix available. Review medium/low suggestions manually.")
    else:
        st.caption("No safe auto-fix available for this field.")


def analyze_placeholders(text: str) -> dict:
    """Analyze placeholder usage stats for health panel."""
    if not text:
        return {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "duplicate_occurrences": 0,
            "duplicate_unique": 0,
            "duplicate_details": {},
            "invalid_tokens": [],
        }

    found = re.findall(r'%%([A-Za-z0-9_]+)%%', text)
    valid = [p for p in found if p in VALID_PLACEHOLDERS]
    invalid = [p for p in found if p not in VALID_PLACEHOLDERS]

    counter = Counter(found)
    duplicates = {k: v for k, v in counter.items() if v > 1}
    duplicate_occurrences = sum(v - 1 for v in duplicates.values())

    return {
        "total": len(found),
        "valid": len(valid),
        "invalid": len(invalid),
        "duplicate_occurrences": duplicate_occurrences,
        "duplicate_unique": len(duplicates),
        "duplicate_details": duplicates,
        "invalid_tokens": sorted(set(invalid)),
    }


def get_placeholder_sample_value(placeholder_name: str) -> str:
    """Return a realistic sample value for a known placeholder."""
    # Hard requirements and explicit high-confidence mappings first
    explicit_values = {
        "BrandName": "Betsson",
        "BrandDomain": "betsson.com",
        "PalantirDomain": "betsson",
        "OfferId": "123456",
        "CampaignEndDateAndTime": "11 Apr 2026 23:59",
        "LastContentChangeLocalTimeStamp": "11 Apr 2026 09:45",
        "CustomerFirstName": "Alex",
        "CustomerLastName": "Johnson",
        "CustomerGuid": "8f3a9c2d",
        "CustomerTotalBalance": "10 €",
        "NrOfFreespins": "50",
        "FreespinGames": "Book of Dead",
        "FreespinValidityDays": "7",
        "FreespinValidityHours": "12",
        "FreespinValue": "10 €",
        "WinningsLifetime": "7 days",
        "WageringRequirementMultiplier": "30x",
        "BonusAmount": "10 €",
        "BonusLifetime": "14 days",
        "BonusDescription": "Casino bonus",
        "CashRewardAmount": "10 €",
        "SBRewardStake": "10 €",
        "SBRewardMinSelections": "3",
        "SBRewardClaimableDuration": "7 days",
        "SBRewardOn": "Sportsbook",
        "TaskMinimumOdds": "1.50",
        "TaskMinimumSelections": "3",
        "TaskIncludedBetTypes": "Single, Acca",
        "TaskIncludedBettingMarkets": "1X2, Over/Under",
        "SBWagerTaskOn": "Sportsbook",
        "WagerTaskOn": "Casino",
        "DepositExcludedPayments": "Skrill, Neteller",
        "DepositFulfillmentAmount": "10 €",
        "NetLossGameplayTaskOn": "Casino",
        "NetLossGameplayPercentage": "10%",
        "NetLossGameplayMinimumAmount": "10 €",
        "NetLossGameplayMaxReceivedAmount": "10 €",
        "NetLossGameplayMinimumGameRounds": "20",
        "NetLossGameplayMinimumStakeRound": "1 €",
        "NetLossSportsbookTaskOn": "Sportsbook",
        "NetLossSportsbookPercentage": "10%",
        "NetLossSportsbookMinimumAmount": "10 €",
        "NetLossSportsbookMaxReceivedAmount": "10 €",
        "NetLossSportsbookMinimumWager": "10 €",
        "NetLossSportsbookMinimumOdds": "1.50",
        "NetLossSportsbookBetType": "Single",
    }

    if placeholder_name in explicit_values:
        return explicit_values[placeholder_name]

    # Heuristics for placeholders not explicitly listed
    name_lower = placeholder_name.lower()

    # User requirement: monetary placeholders should render as 10 €
    money_hints = ["amount", "stake", "value", "balance", "cash", "wager", "minimum"]
    if any(hint in name_lower for hint in money_hints) and "odds" not in name_lower and "days" not in name_lower:
        return "10 €"

    if "percentage" in name_lower:
        return "10%"
    if "odds" in name_lower:
        return "1.50"
    if "days" in name_lower:
        return "7"
    if "hours" in name_lower:
        return "12"
    if "games" in name_lower:
        return "Book of Dead"
    if "brand" in name_lower:
        return "Betsson"

    return "Sample value"


def render_placeholders_campaign_style(html_text: str, mode: str = "realistic") -> str:
    """Render placeholders in preview.

    Modes:
    - realistic: valid placeholders replaced by sample values; invalid shown in red.
    - raw: valid placeholders shown in amber token badges; invalid shown in red.
    """
    if not html_text:
        return ""

    def replacer(match: re.Match) -> str:
        placeholder_name = match.group(1)
        full_token = f"%%{placeholder_name}%%"

        if placeholder_name in VALID_PLACEHOLDERS:
            if mode == "realistic":
                sample_value = get_placeholder_sample_value(placeholder_name)
                return (
                    '<span style="'
                    'background:#e6f4ea;'
                    'color:#1f5f32;'
                    'border:1px dashed #7ac68d;'
                    'border-radius:6px;'
                    'padding:0 4px;'
                    'white-space:nowrap;'
                    'display:inline-block;'
                    '" '
                    f'title="{full_token}">'
                    f'{sample_value}'
                    '</span>'
                )

            # raw mode (default visual style for valid placeholders)
            return (
                '<span style="'
                'background:#ffefbf;'
                'color:#6f5607;'
                'border:1px dashed #d8b45a;'
                'border-radius:6px;'
                'padding:0 4px;'
                'white-space:nowrap;'
                'display:inline-block;'
                '">'
                f'{full_token}'
                '</span>'
            )

        return (
            '<span style="'
            'background:#ffc2bc;'
            'color:#6f1812;'
            'border:1px solid #d97770;'
            'border-radius:6px;'
            'padding:0 4px;'
            'white-space:nowrap;'
            'display:inline-block;'
            '">'
            f'{full_token}'
            '</span>'
        )

    return re.sub(r'%%([A-Za-z0-9_]+)%%', replacer, html_text)


def bbcode_to_html(text: str, highlight_placeholders: bool = True) -> str:
    """Convert BBCode to HTML for preview."""
    if not text:
        return ""
    
    import html as html_module
    
    # First escape HTML special characters
    escaped = html_module.escape(text)
    
    # Then apply BBCode conversions
    html = escaped
    html = re.sub(r'\[b\](.*?)\[/b\]', r'<strong>\1</strong>', html, flags=re.DOTALL)
    html = re.sub(r'\[i\](.*?)\[/i\]', r'<em>\1</em>', html, flags=re.DOTALL)
    html = re.sub(r'\[u\](.*?)\[/u\]', r'<u>\1</u>', html, flags=re.DOTALL)
    html = re.sub(r'\[ul\](.*?)\[/ul\]', r'<ul>\1</ul>', html, flags=re.DOTALL)
    html = re.sub(r'\[ol\](.*?)\[/ol\]', r'<ol>\1</ol>', html, flags=re.DOTALL)
    html = re.sub(r'\[li\](.*?)\[/li\]', r'<li>\1</li>', html, flags=re.DOTALL)
    html = re.sub(r'\[url=(.*?)\](.*?)\[/url\]', r'<a href="\1" style="color: #6db3f2;">\2</a>', html, flags=re.DOTALL)
    
    if highlight_placeholders:
        # Highlight placeholders with a subtle colored badge
        html = re.sub(
            r'%%([A-Za-z0-9_]+)%%',
            r'<code style="background: linear-gradient(135deg, #2d5a27 0%, #1a3d1a 100%); color: #90EE90; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; white-space: nowrap;">%%\1%%</code>',
            html
        )
    
    # Convert newlines to <br>
    html = html.replace('\n', '<br>')
    
    return html


def image_file_to_data_uri(image_path: Path) -> str:
    """Encode a local image file as data URI for HTML preview embedding."""
    if not image_path.exists():
        return ""

    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/jpeg"

    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def render_oms_desktop_preview(title: str, body: str, cta: str, image_data_uri: str, placeholder_mode: str = "realistic") -> str:
    """Render a desktop OMS card preview that mimics production layout."""
    import html as html_module

    safe_title = render_placeholders_campaign_style(html_module.escape(title or ""), mode=placeholder_mode)
    safe_cta = render_placeholders_campaign_style(html_module.escape(cta or "Opt-in"), mode=placeholder_mode)
    received_text = datetime.now().strftime("Received on %A, %d %B %Y at %H:%M")
    safe_received = html_module.escape(received_text)
    body_html = bbcode_to_html(body or "", highlight_placeholders=False)
    body_html = render_placeholders_campaign_style(body_html, mode=placeholder_mode)

    image_html = ""
    if image_data_uri:
        image_html = f'<img src="{image_data_uri}" alt="OMS image" style="width: 54px; height: 54px; border-radius: 8px; object-fit: cover; flex-shrink: 0;">'

    return textwrap.dedent(f"""
    <div style="
        border: 1px solid #d9dde4;
        border-radius: 8px;
        background: #ffffff;
        color: #1b1f24;
        padding: 14px;
        position: relative;
        box-shadow: 0 1px 0 rgba(0,0,0,0.02);
    ">
        <div style="
            position: absolute;
            right: 16px;
            top: 16px;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4a8df6;
        "></div>

        <div style="display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px;">
            {image_html}
            <div style="padding-right: 18px;">
                <div style="font-size: 17px; line-height: 1.3; font-weight: 650; color: #14181d; margin: 0 0 3px 0;">{safe_title}</div>
                <div style="font-size: 14px; color: #5f6b7a;">{safe_received}</div>
            </div>
        </div>

        <div style="font-size: 15px; line-height: 1.42; color: #161b22; margin-top: 6px; margin-bottom: 12px;">
            {body_html}
        </div>

        <div style="display: flex; justify-content: flex-end; align-items: center; gap: 12px; margin-top: 4px;">
            <button style="
                border: 0;
                background: transparent;
                color: #ff6a00;
                font-size: 14px;
                font-weight: 500;
                cursor: default;
            ">Delete</button>
            <button style="
                border: 0;
                border-radius: 6px;
                background: #ff6a00;
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
                padding: 8px 16px;
                cursor: default;
            ">{safe_cta}</button>
        </div>
    </div>
    """).strip()


def check_missing_content(template_type: str, title: str = None, body: str = None, cta: str = None) -> list[str]:
    """Check for missing required content. Returns list of warnings."""
    warnings = []
    
    if template_type == "OMS":
        if not title or not title.strip():
            warnings.append("⚠️ Title is empty")
        if not body or not body.strip():
            warnings.append("⚠️ Body is empty")
        if not cta or not cta.strip():
            warnings.append("⚠️ CTA is empty")
    elif template_type == "SMS":
        if not body or not body.strip():
            warnings.append("⚠️ SMS body is empty")
    
    return warnings


def infer_oms_image_tags(display_name: str, cms_key: str) -> list[str]:
    """Infer lightweight UX tags for fixed OMS image options."""
    tags: list[str] = []
    name = (display_name or "").lower()
    key = (cms_key or "").lower()

    if "live casino" in name:
        tags.append("Live Casino")
    elif "sportsbook" in name or "_sb" in key:
        tags.append("Sportsbook")
    elif "casino" in name or "_casino" in key:
        tags.append("Casino")

    if "bonus" in name:
        tags.append("Bonus")
    if "cash" in name:
        tags.append("Cash")
    if "free spin" in name or "freespin" in key:
        tags.append("Free Spin")
    if "free bet" in name:
        tags.append("Free Bet")
    if "risk free" in name:
        tags.append("Risk Free")
    if "money" in name:
        tags.append("Money")
    if "default" in name:
        tags.append("Fallback")

    unique_tags: list[str] = []
    for tag in tags:
        if tag not in unique_tags:
            unique_tags.append(tag)

    return unique_tags


def format_oms_image_option(display_name: str) -> str:
    """Create richer dropdown labels while keeping source image names unchanged."""
    image_tuple = OMS_IMAGES.get(display_name)
    if not image_tuple:
        return display_name

    cms_key = image_tuple[0]
    tags = infer_oms_image_tags(display_name, cms_key)
    if not tags:
        return display_name

    return f"{display_name} | {' • '.join(tags)}"


def detect_offer_type(parsed_docs: list) -> dict:
    """
    Auto-detect task type, reward type, and recommended image from content.
    Analyzes keywords in templates across all documents.
    Returns dict with detected values and confidence.
    """
    # Collect all text content for analysis
    all_text = ""
    for doc in parsed_docs:
        if doc.launch_oms:
            for t in doc.launch_oms.templates:
                all_text += f" {t.title or ''} {t.body or ''}"
        if doc.reminder_oms:
            for t in doc.reminder_oms.templates:
                all_text += f" {t.title or ''} {t.body or ''}"
        if doc.launch_sms:
            for t in doc.launch_sms.templates:
                all_text += f" {t.body or ''}"
        if doc.my_offers:
            all_text += f" {doc.my_offers.task or ''} {doc.my_offers.reward or ''}"
    
    all_text_lower = all_text.lower()
    
    # Detect Task Type
    task_type = None
    task_confidence = "low"
    
    # Check for placeholders first (highest confidence)
    if "%%depositfulfillmentamount%%" in all_text_lower or "%%depositexcludedpayments%%" in all_text_lower:
        task_type = "DepositTask"
        task_confidence = "high"
    elif "%%sbwagertaskon%%" in all_text_lower or "%%taskminimumodds%%" in all_text_lower:
        task_type = "PlaceBetWithSettlement"
        task_confidence = "high"
    elif "%%wagertaskon%%" in all_text_lower and "%%sbwagertaskon%%" not in all_text_lower:
        task_type = "Wager"
        task_confidence = "high"
    elif "%%netlossgameplay%%" in all_text_lower:
        task_type = "NetLossGameplay"
        task_confidence = "high"
    elif "%%netlosssportsbook%%" in all_text_lower:
        task_type = "NetLossSportsbook"
        task_confidence = "high"
    # Keyword detection (medium confidence)
    elif any(kw in all_text_lower for kw in ["deposit", "deposita", "déposer", "einzahlung", "talletaa"]):
        task_type = "DepositTask"
        task_confidence = "medium"
    elif any(kw in all_text_lower for kw in ["bet on", "place a bet", "apuesta", "wager on sports", "sportsbook bet"]):
        task_type = "PlaceBetWithSettlement"
        task_confidence = "medium"
    elif any(kw in all_text_lower for kw in ["wager", "play through", "bet through"]):
        task_type = "Wager"
        task_confidence = "medium"
    elif any(kw in all_text_lower for kw in ["cashback", "net loss"]):
        task_type = "NetLossGameplay"
        task_confidence = "medium"
    
    # Detect Reward Type
    reward_type = None
    reward_confidence = "low"
    is_cash = False  # Track if reward is cash vs bonus
    
    # Check for placeholders first
    if "%%nroffreespins%%" in all_text_lower or "%%freespingames%%" in all_text_lower:
        # Determine if cash or bonus free spins
        if any(kw in all_text_lower for kw in ["cash free spin", "cash spin", "free cash spin", "withdrawable", "efectivo", "μετρητά"]):
            reward_type = "CashFreespin"
            is_cash = True
        else:
            reward_type = "Freespin"
        reward_confidence = "high"
    elif "%%bonusamount%%" in all_text_lower:
        reward_type = "BonusMoney"
        reward_confidence = "high"
    elif "%%cashrewardamount%%" in all_text_lower:
        reward_type = "CashMoney"
        is_cash = True
        reward_confidence = "high"
    elif "%%sbrewardstake%%" in all_text_lower:
        # Free bet reward
        if any(kw in all_text_lower for kw in ["risk-free", "risk free"]):
            reward_type = "RiskFreeBet" if not is_cash else "CashRiskFreeBet"
        else:
            reward_type = "FreeBet" if not is_cash else "CashFreeBet"
        reward_confidence = "high"
    # Keyword detection
    elif any(kw in all_text_lower for kw in ["free spin", "freespin", "giros gratis", "free cash spin"]):
        if "cash" in all_text_lower or "efectivo" in all_text_lower or "withdrawable" in all_text_lower:
            reward_type = "CashFreespin"
            is_cash = True
        else:
            reward_type = "Freespin"
        reward_confidence = "medium"
    elif any(kw in all_text_lower for kw in ["free bet", "freebet", "apuesta gratis"]):
        if "risk" in all_text_lower:
            reward_type = "RiskFreeBet"
        else:
            reward_type = "FreeBet"
        reward_confidence = "medium"
    elif any(kw in all_text_lower for kw in ["bonus money", "bonus cash", "dinero de bono"]):
        reward_type = "BonusMoney"
        reward_confidence = "medium"
    
    # Detect context (Casino vs Sportsbook)
    is_sportsbook = any(kw in all_text_lower for kw in [
        "sportsbook", "sports", "bet on", "odds", "apuesta deportiva", 
        "%%sbwagertaskon%%", "%%taskminimumodds%%"
    ])
    is_live_casino = "live casino" in all_text_lower or "live dealer" in all_text_lower
    
    # Recommend Image based on detected reward and context
    recommended_image = None
    if reward_type:
        if reward_type == "CashFreespin":
            recommended_image = "Cash Free Spin (Casino)"
        elif reward_type == "Freespin":
            recommended_image = "Bonus Free Spin (Casino)"
        elif reward_type in ["FreeBet", "CashFreeBet"]:
            if is_cash or reward_type == "CashFreeBet":
                recommended_image = "Cash Free Bet (Sportsbook)"
            else:
                recommended_image = "Bonus Free Bet (Sportsbook)"
        elif reward_type in ["RiskFreeBet", "CashRiskFreeBet"]:
            if is_cash:
                recommended_image = "Cash Risk Free Bet (Sportsbook)"
            else:
                recommended_image = "Bonus Risk Free Bet (Sportsbook)"
        elif reward_type == "BonusMoney":
            if is_sportsbook:
                recommended_image = "Bonus Money (Sportsbook)"
            elif is_live_casino:
                recommended_image = "Live Casino - Wager&Get Bonus A"
            else:
                recommended_image = "Bonus Money (Casino)"
        elif reward_type == "CashMoney":
            recommended_image = "Cash Money (Casino)"
    
    return {
        "task_type": task_type,
        "task_confidence": task_confidence,
        "reward_type": reward_type,
        "reward_confidence": reward_confidence,
        "recommended_image": recommended_image,
        "is_sportsbook": is_sportsbook,
        "is_live_casino": is_live_casino,
    }


def check_template_consistency(parsed_docs: list) -> dict:
    """
    Check that all languages have consistent template variants.
    Returns dict with consistency report.
    """
    report = {
        "is_consistent": True,
        "issues": [],
        "by_language": {},
    }
    
    # Collect variants per language
    for doc in parsed_docs:
        lang = doc.language_code
        variants = {
            "launch_oms": set(),
            "reminder_oms": set(),
            "reward_oms": set(),
            "launch_sms": set(),
            "reminder_sms": set(),
        }
        
        if doc.launch_oms:
            variants["launch_oms"] = {t.variant for t in doc.launch_oms.templates}
        if doc.reminder_oms:
            variants["reminder_oms"] = {t.variant for t in doc.reminder_oms.templates}
        if doc.reward_oms:
            variants["reward_oms"] = {t.variant for t in doc.reward_oms.templates}
        if doc.launch_sms:
            variants["launch_sms"] = {t.variant for t in doc.launch_sms.templates}
        if doc.reminder_sms:
            variants["reminder_sms"] = {t.variant for t in doc.reminder_sms.templates}
        
        report["by_language"][lang] = variants
    
    # Compare all languages against the first one (reference)
    if len(parsed_docs) > 1:
        ref_lang = parsed_docs[0].language_code
        ref_variants = report["by_language"][ref_lang]
        
        for lang, variants in report["by_language"].items():
            if lang == ref_lang:
                continue
            
            for section in ["launch_oms", "reminder_oms", "reward_oms", "launch_sms", "reminder_sms"]:
                ref_set = ref_variants[section]
                lang_set = variants[section]
                
                missing = ref_set - lang_set
                extra = lang_set - ref_set
                
                if missing:
                    report["is_consistent"] = False
                    section_name = section.replace("_", " ").title()
                    report["issues"].append(f"❌ {lang}: Missing {section_name} variants: {', '.join(sorted(missing))}")
                
                if extra:
                    report["is_consistent"] = False
                    section_name = section.replace("_", " ").title()
                    report["issues"].append(f"⚠️ {lang}: Extra {section_name} variants: {', '.join(sorted(extra))}")
    
    return report


def generate_missing_content_report(parsed_docs: list) -> dict:
    """
    Generate a comprehensive missing content report across all languages.
    """
    report = {
        "total_issues": 0,
        "by_language": {},
        "summary": [],
    }
    
    for doc in parsed_docs:
        lang = doc.language_code
        issues = []
        
        # Check OMS templates
        if not doc.launch_oms or not doc.launch_oms.templates:
            issues.append("❌ No Launch OMS templates")
        else:
            for t in doc.launch_oms.templates:
                if not t.title or not t.title.strip():
                    issues.append(f"⚠️ Launch OMS {t.variant}: Missing title")
                if not t.body or not t.body.strip():
                    issues.append(f"⚠️ Launch OMS {t.variant}: Missing body")
                if not t.cta or not t.cta.strip():
                    issues.append(f"⚠️ Launch OMS {t.variant}: Missing CTA")
        
        if not doc.reminder_oms or not doc.reminder_oms.templates:
            issues.append("❌ No Reminder OMS templates")
        else:
            for t in doc.reminder_oms.templates:
                if not t.title or not t.title.strip():
                    issues.append(f"⚠️ Reminder OMS {t.variant}: Missing title")
                if not t.body or not t.body.strip():
                    issues.append(f"⚠️ Reminder OMS {t.variant}: Missing body")
                if not t.cta or not t.cta.strip():
                    issues.append(f"⚠️ Reminder OMS {t.variant}: Missing CTA")
        
        # Check SMS templates
        if not doc.launch_sms or not doc.launch_sms.templates:
            issues.append("❌ No Launch SMS templates")
        else:
            for t in doc.launch_sms.templates:
                if not t.body or not t.body.strip():
                    issues.append(f"⚠️ Launch SMS {t.variant}: Missing body")
        
        if not doc.reminder_sms or not doc.reminder_sms.templates:
            issues.append("❌ No Reminder SMS templates")
        else:
            for t in doc.reminder_sms.templates:
                if not t.body or not t.body.strip():
                    issues.append(f"⚠️ Reminder SMS {t.variant}: Missing body")
        
        # Check T&C
        if not doc.tc:
            issues.append("❌ No T&C section found")
        else:
            if not doc.tc.significant_terms or not doc.tc.significant_terms.strip():
                issues.append("⚠️ T&C: Missing significant terms")
            if not doc.tc.terms_and_conditions or not doc.tc.terms_and_conditions.strip():
                issues.append("⚠️ T&C: Missing full terms")
        
        report["by_language"][lang] = issues
        report["total_issues"] += len(issues)
    
    # Generate summary
    languages_with_issues = [lang for lang, issues in report["by_language"].items() if issues]
    if languages_with_issues:
        report["summary"].append(f"⚠️ {len(languages_with_issues)}/{len(parsed_docs)} languages have issues")
    else:
        report["summary"].append("✅ All languages have complete content")
    
    return report


def generate_invalid_placeholder_report(parsed_docs: list) -> dict:
    """Generate invalid placeholder report across all languages."""
    report = {
        "total_invalid_occurrences": 0,
        "by_language": {},
    }

    for doc in parsed_docs:
        lang = doc.language_code
        invalid_tokens: list[str] = []

        # OMS
        if doc.launch_oms:
            for t in doc.launch_oms.templates:
                invalid_tokens.extend(validate_placeholders((t.title or "") + " " + (t.body or "") + " " + (t.cta or "")))
        if doc.reminder_oms:
            for t in doc.reminder_oms.templates:
                invalid_tokens.extend(validate_placeholders((t.title or "") + " " + (t.body or "") + " " + (t.cta or "")))
        if doc.reward_oms:
            for t in doc.reward_oms.templates:
                invalid_tokens.extend(validate_placeholders((t.title or "") + " " + (t.body or "") + " " + (t.cta or "")))

        # SMS
        if doc.launch_sms:
            for t in doc.launch_sms.templates:
                invalid_tokens.extend(validate_placeholders(t.body or ""))
        if doc.reminder_sms:
            for t in doc.reminder_sms.templates:
                invalid_tokens.extend(validate_placeholders(t.body or ""))

        # T&C
        if doc.tc:
            invalid_tokens.extend(validate_placeholders((doc.tc.significant_terms or "") + " " + (doc.tc.terms_and_conditions or "")))

        report["by_language"][lang] = {
            "count": len(invalid_tokens),
            "tokens": sorted(set(invalid_tokens)),
        }
        report["total_invalid_occurrences"] += len(invalid_tokens)

    return report


def build_language_readiness(parsed_docs: list) -> dict:
    """Build per-language QA readiness summary from missing + invalid checks."""
    missing_report = generate_missing_content_report(parsed_docs)
    invalid_report = generate_invalid_placeholder_report(parsed_docs)
    language_mismatch_report = generate_language_mismatch_report(parsed_docs)

    by_language = {}
    ready_count = 0
    missing_count = 0
    invalid_count = 0
    mismatch_count = 0

    for doc in parsed_docs:
        lang = doc.language_code
        has_missing = len(missing_report["by_language"].get(lang, [])) > 0
        invalid_total = invalid_report["by_language"].get(lang, {}).get("count", 0)
        mismatch_info = language_mismatch_report.get(lang, {})
        has_mismatch = mismatch_info.get("mismatch", False)

        if invalid_total > 0:
            status = "invalid"
            invalid_count += 1
        elif has_missing:
            status = "missing"
            missing_count += 1
        else:
            status = "ready"
            ready_count += 1

        if has_mismatch:
            mismatch_count += 1

        by_language[lang] = {
            "status": status,
            "missing_issues": missing_report["by_language"].get(lang, []),
            "invalid_count": invalid_total,
            "invalid_tokens": invalid_report["by_language"].get(lang, {}).get("tokens", []),
            "language_mismatch": {
                "detected": has_mismatch,
                "detected_lang": mismatch_info.get("detected_language"),
                "reason": mismatch_info.get("reason"),
            },
        }

    return {
        "by_language": by_language,
        "ready_count": ready_count,
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "mismatch_count": mismatch_count,
        "has_issues": (missing_count + invalid_count + mismatch_count) > 0,
    }


def detect_markets_from_languages(parsed_docs: list) -> list[str]:
    """
    Auto-detect markets from uploaded document languages.
    Returns list of unique market names based on LANGUAGE_TO_MARKET mapping.
    """
    markets = set()
    for doc in parsed_docs:
        lang_code = doc.language_code
        if lang_code in LANGUAGE_TO_MARKET:
            markets.add(LANGUAGE_TO_MARKET[lang_code])
    return sorted(list(markets))


def get_editor_store() -> dict[str, str]:
    """Return persistent editor value store that survives widget cleanup across reruns."""
    if "editor_values" not in st.session_state:
        st.session_state["editor_values"] = {}
    return st.session_state["editor_values"]


def set_editor_value(widget_key: str, value: str) -> None:
    """Persist current editor value outside widget-managed session state."""
    get_editor_store()[widget_key] = value or ""


def get_editor_value(widget_key: str, fallback_value: str) -> str:
    """Read current value from persistent editor store, widget state, or fallback."""
    editor_store = get_editor_store()
    if widget_key in st.session_state:
        return st.session_state.get(widget_key, fallback_value or "")
    if widget_key in editor_store:
        return editor_store.get(widget_key, fallback_value or "")
    return fallback_value or ""


def sync_fix_buffer_to_widget(widget_key: str, fallback_value: str) -> None:
    """Apply pending fix buffer into both widget state and persistent editor store."""
    fix_buffer_key = f"fix_buffer_{widget_key}"
    if fix_buffer_key in st.session_state:
        buffered_value = st.session_state[fix_buffer_key]
        st.session_state[widget_key] = buffered_value
        set_editor_value(widget_key, buffered_value)
        del st.session_state[fix_buffer_key]
    elif widget_key not in st.session_state:
        st.session_state[widget_key] = get_editor_value(widget_key, fallback_value)


def get_effective_widget_value(widget_key: str, fallback_value: str) -> str:
    """Return current value for a field, preferring fix buffer over widget state."""
    fix_key = f"fix_buffer_{widget_key}"
    if fix_key in st.session_state:
        return st.session_state.get(fix_key, fallback_value or "")
    return get_editor_value(widget_key, fallback_value)


def build_effective_parsed_docs(parsed_docs: list[ParsedDocument]) -> list[ParsedDocument]:
    """Clone parsed docs and apply in-app edits from session state for consistent QA checks."""
    effective_docs = copy.deepcopy(parsed_docs)

    for doc in effective_docs:
        lang = doc.language_code

        sms_idx = 0
        if doc.launch_sms:
            for template in doc.launch_sms.templates:
                key = f"sms_{lang}_{sms_idx}_Launch_{template.variant}"
                template.body = get_effective_widget_value(key, template.body or "")
                sms_idx += 1
        if doc.reminder_sms:
            for template in doc.reminder_sms.templates:
                key = f"sms_{lang}_{sms_idx}_Reminder_{template.variant}"
                template.body = get_effective_widget_value(key, template.body or "")
                sms_idx += 1

        oms_idx = 0
        if doc.launch_oms:
            for template in doc.launch_oms.templates:
                title_key = f"oms_title_{lang}_{oms_idx}_Launch_{template.variant}"
                body_key = f"oms_body_{lang}_{oms_idx}_Launch_{template.variant}"
                cta_key = f"oms_cta_{lang}_{oms_idx}_Launch_{template.variant}"
                template.title = get_effective_widget_value(title_key, template.title or "")
                template.body = get_effective_widget_value(body_key, template.body or "")
                template.cta = get_effective_widget_value(cta_key, template.cta or "")
                oms_idx += 1

        if doc.reminder_oms:
            for template in doc.reminder_oms.templates:
                title_key = f"oms_title_{lang}_{oms_idx}_Reminder_{template.variant}"
                body_key = f"oms_body_{lang}_{oms_idx}_Reminder_{template.variant}"
                cta_key = f"oms_cta_{lang}_{oms_idx}_Reminder_{template.variant}"
                template.title = get_effective_widget_value(title_key, template.title or "")
                template.body = get_effective_widget_value(body_key, template.body or "")
                template.cta = get_effective_widget_value(cta_key, template.cta or "")
                oms_idx += 1

        if doc.reward_oms:
            for template in doc.reward_oms.templates:
                title_key = f"oms_title_{lang}_{oms_idx}_Reward_{template.variant}"
                body_key = f"oms_body_{lang}_{oms_idx}_Reward_{template.variant}"
                cta_key = f"oms_cta_{lang}_{oms_idx}_Reward_{template.variant}"
                template.title = get_effective_widget_value(title_key, template.title or "")
                template.body = get_effective_widget_value(body_key, template.body or "")
                template.cta = get_effective_widget_value(cta_key, template.cta or "")
                oms_idx += 1

        if doc.tc:
            sig_key = f"tc_sig_{lang}"
            full_key = f"tc_full_{lang}"
            doc.tc.significant_terms = get_effective_widget_value(sig_key, doc.tc.significant_terms or "")
            doc.tc.terms_and_conditions = get_effective_widget_value(full_key, doc.tc.terms_and_conditions or "")

    return effective_docs


def extract_xml_from_cms_export(zip_file) -> dict[str, str]:
    """
    Extract XML content from a CMS export ZIP.
    Returns dict of {filename: xml_content}
    """
    xml_files = {}
    with zipfile.ZipFile(zip_file, 'r') as zf:
        for name in zf.namelist():
            if name.endswith('.xml'):
                try:
                    content = zf.read(name).decode('utf-8-sig')  # Handle BOM
                    xml_files[name] = content
                except Exception:
                    pass
    return xml_files


def format_xml_for_diff(xml_content: str) -> str:
    """
    Pretty-print XML for easier diff comparison.
    """
    try:
        # Parse and re-format
        root = ET.fromstring(xml_content.encode('utf-8'))
        ET.indent(root)
        return ET.tostring(root, encoding='unicode')
    except Exception:
        # If parsing fails, return as-is
        return xml_content


def generate_diff_html(old_text: str, new_text: str, old_label: str = "Existing", new_label: str = "Generated") -> str:
    """
    Generate HTML diff between two texts.
    """
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    
    differ = difflib.HtmlDiff(wrapcolumn=80)
    html = differ.make_table(old_lines, new_lines, fromdesc=old_label, todesc=new_label, context=True, numlines=3)
    
    # Add some styling
    styled_html = f"""
    <style>
        .diff_add {{ background-color: #aaffaa; }}
        .diff_sub {{ background-color: #ffaaaa; }}
        .diff_chg {{ background-color: #ffffaa; }}
        table.diff {{ font-family: monospace; font-size: 12px; border-collapse: collapse; width: 100%; }}
        table.diff td {{ padding: 2px 5px; border: 1px solid #ddd; }}
        table.diff th {{ background-color: #f0f0f0; padding: 5px; }}
    </style>
    {html}
    """
    return styled_html


# Page config
brand_logo_path, brand_favicon_path, brand_favicon_black_path = ensure_brand_assets()

st.set_page_config(
    page_title="CMS Template Generator",
    page_icon=str(brand_favicon_black_path),
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    /* Betsson Sans: Local woff2 files for maximum performance */
    @font-face {
        font-family: "Betsson Sans";
        font-style: normal;
        font-weight: 400;
        src: url("./app/images/brand/BetssonSans-Regular.woff2") format("woff2"),
             url("https://www.betsson.com/wp-content/themes/betsson-theme/assets/fonts/betsson-sans/BetssonSans-Regular.woff2") format("woff2");
        font-display: swap;
    }

    @font-face {
        font-family: "Betsson Sans";
        font-style: normal;
        font-weight: 600;
        src: url("./app/images/brand/BetssonSans-SemiBold.woff2") format("woff2"),
             url("https://www.betsson.com/wp-content/themes/betsson-theme/assets/fonts/betsson-sans/BetssonSans-SemiBold.woff2") format("woff2");
        font-display: swap;
    }

    @font-face {
        font-family: "Betsson Sans";
        font-style: normal;
        font-weight: 700;
        src: url("./app/images/brand/BetssonSans-Bold.woff2") format("woff2"),
             url("https://www.betsson.com/wp-content/themes/betsson-theme/assets/fonts/betsson-sans/BetssonSans-Bold.woff2") format("woff2");
        font-display: swap;
    }

    @font-face {
        font-family: "Betsson Sans";
        font-style: normal;
        font-weight: 900;
        src: url("./app/images/brand/BetssonSans-Black.woff2") format("woff2"),
             url("https://www.betsson.com/wp-content/themes/betsson-theme/assets/fonts/betsson-sans/BetssonSans-Black.woff2") format("woff2");
        font-display: swap;
    }

    /* Open Sans: Fallback for body and UI text */
    @font-face {
        font-family: "Open Sans";
        font-style: normal;
        font-weight: 400;
        src: url("https://fonts.gstatic.com/s/opensans/v35/memSYaGs126MiZpBA-UvWbX5ZZdhS6IgoI7JY4TQyVY.woff2") format("woff2");
        font-display: swap;
    }

    @font-face {
        font-family: "Open Sans";
        font-style: normal;
        font-weight: 600;
        src: url("https://fonts.gstatic.com/s/opensans/v35/memQYaGs126MiZpBA-UFWbXpF7b2E-IoF23CsT_Ud-0.woff2") format("woff2");
        font-display: swap;
    }

    @font-face {
        font-family: "Open Sans";
        font-style: normal;
        font-weight: 700;
        src: url("https://fonts.gstatic.com/s/opensans/v35/memQYaGs126MiZpBA-UFWbXpF7b2E-IoL0SwMCRvDY.woff2") format("woff2");
        font-display: swap;
    }

    :root {
        /* Betsson 2025 Brand Palette */
        --bs-primary: #00A651;
        --bs-primary-light: rgba(0, 166, 81, 0.1);
        --bs-secondary: #FF6600;
        --bs-secondary-dark: #E45D1C;
        --bs-black: #1F1F1F;
        --bs-violet: #5404CD;
        --bs-violet-light: rgba(84, 4, 205, 0.1);
        --bs-light-gray: #F2F2F2;
        --bs-light-gray-dark: #E5E5E5;
        
        /* Existing app palette (for compatibility) */
        --rc-bg: #0e1218;
        --rc-panel: #141b24;
        --rc-panel-soft: #101720;
        --rc-border: #263243;
        --rc-text: #e9eef5;
        --rc-muted: #92a2b6;
        --rc-green: #64d596;
        --rc-green-bg: rgba(100, 213, 150, 0.12);
        --rc-amber: #f4c96b;
        --rc-amber-bg: rgba(244, 201, 107, 0.14);
        --rc-red: #ef8b86;
        --rc-red-bg: rgba(239, 139, 134, 0.14);
        --rc-blue: #7db7ff;
        --rc-blue-bg: rgba(125, 183, 255, 0.12);
        --rc-brand: #FF6600;
        --rc-brand-2: #fd9455;
        --rc-brand-hover: #ff8533;
        --rc-brand-active: #E45D1C;
    }

    .stApp {
        font-family: "Open Sans", Arial, sans-serif;
        background:
            /* Betsson polyform blob — top right, orange glow */
            radial-gradient(ellipse 60% 40% at 95% 5%, rgba(255, 102, 0, 0.18), transparent 55%),
            /* Violet accent — bottom left */
            radial-gradient(ellipse 50% 35% at 5% 95%, rgba(84, 4, 205, 0.12), transparent 55%),
            /* Blue-grey mid atmosphere */
            radial-gradient(circle at 55% 50%, rgba(68, 92, 132, 0.08), transparent 50%),
            /* Base dark */
            linear-gradient(180deg, #0c1117 0%, #090d12 100%);
    }

    h1, h2, h3, h4, h5, h6,
    .stMarkdown h1,
    .stMarkdown h2,
    .stMarkdown h3 {
        font-family: "Betsson Sans", "Open Sans", Arial, sans-serif;
        letter-spacing: -0.02em;
        font-weight: 700;
    }

    .stMarkdown p,
    .stCaption,
    .stText,
    label,
    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        font-family: "Open Sans", Arial, sans-serif;
    }

    .stAlert > div {
        padding: 0.5rem 1rem;
    }

    /* Empty state card */
    .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        padding: 64px 40px;
        border-radius: 24px;
        border: 1.5px dashed rgba(255, 102, 0, 0.3);
        background:
            radial-gradient(ellipse 70% 60% at 50% 0%, rgba(255, 102, 0, 0.07), transparent 60%),
            radial-gradient(ellipse 50% 40% at 100% 100%, rgba(84, 4, 205, 0.07), transparent 60%),
            linear-gradient(135deg, rgba(20, 27, 36, 0.95), rgba(13, 19, 27, 0.98));
        position: relative;
        overflow: hidden;
        margin: 8px 0 24px 0;
    }

    /* Decorative polyform glow for empty state */
    .empty-state::before {
        content: '';
        position: absolute;
        top: -60px;
        right: -60px;
        width: 260px;
        height: 260px;
        background: radial-gradient(circle at 35% 35%, rgba(255, 102, 0, 0.22), transparent 65%);
        border-radius: 60% 40% 30% 70% / 50% 60% 40% 50%;
        pointer-events: none;
    }

    .empty-state::after {
        content: '';
        position: absolute;
        bottom: -40px;
        left: -40px;
        width: 180px;
        height: 180px;
        background: radial-gradient(circle at 60% 60%, rgba(84, 4, 205, 0.15), transparent 65%);
        border-radius: 40% 60% 70% 30%;
        pointer-events: none;
    }

    .empty-state-icon {
        font-size: 3.5rem;
        margin-bottom: 20px;
        position: relative;
        z-index: 1;
    }

    .empty-state-title {
        font-family: "Betsson Sans", "Open Sans", Arial, sans-serif;
        font-size: 1.6rem;
        font-weight: 700;
        color: var(--rc-text);
        margin: 0 0 12px 0;
        letter-spacing: -0.02em;
        position: relative;
        z-index: 1;
    }

    .empty-state-body {
        color: var(--rc-muted);
        font-size: 1rem;
        line-height: 1.7;
        max-width: 360px;
        margin: 0 0 24px 0;
        position: relative;
        z-index: 1;
    }

    .empty-state-hint {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(255, 102, 0, 0.1);
        border: 1px solid rgba(255, 102, 0, 0.25);
        border-radius: 24px;
        padding: 10px 18px;
        color: var(--rc-brand);
        font-size: 0.9rem;
        font-weight: 600;
        position: relative;
        z-index: 1;
    }

    .review-hero {
        background: linear-gradient(135deg, rgba(22, 31, 42, 0.96), rgba(15, 22, 31, 0.96));
        border: 1px solid var(--rc-border);
        border-radius: 20px;
        padding: 32px 28px;
        margin: 0 0 24px 0;
        box-shadow: 0 16px 40px rgba(0, 0, 0, 0.22);
    }

    .review-hero-head {
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 6px;
    }

    .review-hero-logo {
        height: 40px;
        width: auto;
        display: block;
    }

    .review-hero h1 {
        margin: 0;
        font-size: 2.2rem;
        font-weight: 700;
        color: var(--rc-text);
        letter-spacing: -0.02em;
    }

    .review-hero p {
        margin: 10px 0 20px 0;
        color: var(--rc-muted);
        font-size: 1rem;
        line-height: 1.5;
    }

    .hero-meta {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
    }

    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(125, 183, 255, 0.2);
        border-radius: 999px;
        padding: 8px 14px;
        color: var(--rc-text);
        font-size: 0.92rem;
    }

    .hero-pill .label {
        color: var(--rc-muted);
        font-weight: 500;
    }

    .console-strip {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 12px;
        margin: 0 0 20px 0;
    }

    .console-metric {
        background: var(--rc-panel);
        border: 1px solid var(--rc-border);
        border-radius: 16px;
        padding: 16px 18px;
    }

    .console-metric .label {
        color: var(--rc-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-size: 0.72rem;
        margin-bottom: 6px;
    }

    .console-metric .value {
        color: var(--rc-text);
        font-size: 1.5rem;
        font-weight: 700;
        line-height: 1.1;
    }

    .console-metric .sub {
        color: var(--rc-muted);
        font-size: 0.84rem;
        margin-top: 4px;
    }

    /* Badge and highlight styles (Betsson Violet) */
    .badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: var(--bs-violet-light);
        border: 1px solid var(--bs-violet);
        color: var(--bs-violet);
        border-radius: 14px;
        padding: 4px 10px;
        font-size: 0.82rem;
        font-weight: 600;
    }

    .badge.success {
        background: rgba(100, 213, 150, 0.12);
        border-color: rgba(100, 213, 150, 0.32);
        color: var(--rc-green);
    }

    .highlight {
        background: var(--bs-violet-light);
        color: var(--bs-violet);
        padding: 2px 6px;
        border-radius: 4px;
        font-weight: 600;
    }

    .metric-ready { border-color: rgba(100, 213, 150, 0.26); background: linear-gradient(180deg, var(--rc-green-bg), rgba(20,27,36,0.98)); }
    .metric-missing { border-color: rgba(244, 201, 107, 0.26); background: linear-gradient(180deg, var(--rc-amber-bg), rgba(20,27,36,0.98)); }
    .metric-invalid { border-color: rgba(239, 139, 134, 0.26); background: linear-gradient(180deg, var(--rc-red-bg), rgba(20,27,36,0.98)); }
    .metric-session { border-color: rgba(125, 183, 255, 0.24); background: linear-gradient(180deg, var(--rc-blue-bg), rgba(20,27,36,0.98)); }

    /* Metric card buttons — all 5 tiles use the same card shape */
    .st-key-metric_ready div[data-testid="stButton"] button,
    .st-key-metric_missing div[data-testid="stButton"] button,
    .st-key-metric_invalid div[data-testid="stButton"] button,
    .st-key-qa_toggle_issue_actions_from_metric div[data-testid="stButton"] button,
    .st-key-metric_resolved div[data-testid="stButton"] button {
        width: 100% !important;
        min-height: 90px !important;
        border-radius: 16px !important;
        padding: 16px 18px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        transform: none !important;
        box-shadow: none !important;
        transition: all 0.2s ease-in-out !important;
    }

    /* Per-card gradient colors */
    .st-key-metric_ready div[data-testid="stButton"] button { background: linear-gradient(180deg, var(--rc-green-bg), rgba(20,27,36,0.98)) !important; border: 1px solid rgba(100, 213, 150, 0.26) !important; cursor: pointer !important; }
    .st-key-metric_missing div[data-testid="stButton"] button { background: linear-gradient(180deg, var(--rc-amber-bg), rgba(20,27,36,0.98)) !important; border: 1px solid rgba(244, 201, 107, 0.26) !important; cursor: pointer !important; }
    .st-key-metric_invalid div[data-testid="stButton"] button { background: linear-gradient(180deg, var(--rc-red-bg), rgba(20,27,36,0.98)) !important; border: 1px solid rgba(239, 139, 134, 0.26) !important; cursor: pointer !important; }
    .st-key-qa_toggle_issue_actions_from_metric div[data-testid="stButton"] button { background: linear-gradient(180deg, var(--rc-amber-bg), rgba(20,27,36,0.98)) !important; border: 1px solid rgba(244, 201, 107, 0.26) !important; cursor: pointer !important; }
    .st-key-metric_resolved div[data-testid="stButton"] button { background: linear-gradient(180deg, var(--rc-blue-bg), rgba(20,27,36,0.98)) !important; border: 1px solid rgba(125, 183, 255, 0.24) !important; cursor: default !important; }

    /* Text styling for all metric cards */
    .st-key-metric_ready div[data-testid="stButton"] button p,
    .st-key-metric_missing div[data-testid="stButton"] button p,
    .st-key-metric_invalid div[data-testid="stButton"] button p,
    .st-key-qa_toggle_issue_actions_from_metric div[data-testid="stButton"] button p,
    .st-key-metric_resolved div[data-testid="stButton"] button p {
        color: var(--rc-text) !important;
        text-align: center !important;
        white-space: pre-line !important;
        margin: 0 !important;
        line-height: 1.45 !important;
        width: 100% !important;
    }

    /* Hover effect on clickable cards (interactive) */
    .st-key-metric_ready div[data-testid="stButton"] button:hover,
    .st-key-metric_missing div[data-testid="stButton"] button:hover,
    .st-key-metric_invalid div[data-testid="stButton"] button:hover,
    .st-key-qa_toggle_issue_actions_from_metric div[data-testid="stButton"] button:hover {
        filter: brightness(1.15) !important;
        transform: none !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25) !important;
    }

    /* Suppress hover on static (read-only) card */
    .st-key-metric_resolved div[data-testid="stButton"] button:hover {
        transform: none !important;
        box-shadow: none !important;
        filter: none !important;
    

    /* Hover on the clickable mismatch card */
    .st-key-qa_toggle_issue_actions_from_metric div[data-testid="stButton"] button:hover:not([disabled]) {
        cursor: pointer !important;
        border-color: rgba(244, 201, 107, 0.5) !important;
        background: linear-gradient(180deg, rgba(244, 201, 107, 0.2), rgba(20,27,36,0.98)) !important;
        transform: translateY(-1px) !important;
    }

    /* Mismatch card disabled state */
    .st-key-qa_toggle_issue_actions_from_metric div[data-testid="stButton"] button[disabled] {
        opacity: 0.55 !important;
        filter: saturate(0.7) !important;
        cursor: default !important;
    }

    .chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 0 0 14px 0;
    }

    .issue-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border-radius: 999px;
        padding: 7px 11px;
        font-size: 0.88rem;
        border: 1px solid var(--rc-border);
        color: var(--rc-text);
        background: var(--rc-panel-soft);
    }

    .issue-chip.warning {
        border-color: rgba(244, 201, 107, 0.32);
        background: var(--rc-amber-bg);
    }

    .issue-chip.error {
        border-color: rgba(239, 139, 134, 0.32);
        background: var(--rc-red-bg);
    }

    .console-panel {
        background: linear-gradient(180deg, rgba(20, 27, 36, 0.98), rgba(14, 19, 26, 0.98));
        border: 1px solid var(--rc-border);
        border-radius: 16px;
        padding: 20px 22px;
        margin-bottom: 20px;
    }

    .console-panel-title {
        margin: 0 0 8px 0;
        color: var(--rc-text);
        font-size: 1.1rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.02em;
    }

    .console-panel-subtitle {
        margin: 0;
        color: var(--rc-muted);
        font-size: 0.9rem;
        line-height: 1.5;
    }

    .panel-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 16px;
        margin: 0 0 20px 0;
    }

    .mini-panel {
        background: linear-gradient(180deg, rgba(22, 30, 42, 0.95), rgba(18, 25, 34, 0.95));
        border: 1px solid rgba(55, 75, 100, 0.55);
        border-radius: 16px;
        padding: 18px 20px;
        min-height: 140px;
    }

    .mini-panel h4 {
        margin: 0 0 10px 0;
        color: var(--rc-text);
        font-size: 1rem;
        font-weight: 600;
    }

    .mini-panel p,
    .mini-panel ul {
        margin: 0;
        color: var(--rc-muted);
        font-size: 0.9rem;
        line-height: 1.6;
    }

    .mini-panel ul {
        padding-left: 20px;
    }

    .mini-panel li {
        color: var(--rc-muted);
    }

    .mini-panel strong {
        color: var(--rc-text);
    }

    .mini-panel code {
        background: rgba(125, 183, 255, 0.1);
        color: var(--rc-blue);
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.85rem;
    }

    .section-kicker {
        color: var(--bs-violet);
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-size: 0.75rem;
        margin-bottom: 4px;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(10, 15, 22, 0.98), rgba(8, 12, 18, 0.98));
        border-right: 1px solid rgba(38, 50, 67, 0.55);
    }

    .sidebar-status-wrap {
        display: flex;
        flex-direction: column;
        gap: 8px;
        margin-top: 8px;
    }

    .sidebar-status-pill {
        border: 1px solid var(--rc-border);
        border-radius: 10px;
        padding: 8px 10px;
        font-size: 0.84rem;
        color: var(--rc-text);
        background: rgba(20, 27, 36, 0.72);
    }

    .sidebar-status-pill.ok {
        border-color: rgba(100, 213, 150, 0.32);
        background: rgba(100, 213, 150, 0.1);
    }

    .sidebar-status-pill.warn {
        border-color: rgba(244, 201, 107, 0.32);
        background: rgba(244, 201, 107, 0.1);
    }

    /* === Primary Navigation Tabs === */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255, 255, 255, 0.06);
        border-radius: 12px;
        padding: 4px;
        gap: 2px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        margin-bottom: 28px;
        width: fit-content;
    }

    .stTabs [data-baseweb="tab"] {
        font-family: "Open Sans", Arial, sans-serif !important;
        font-size: 0.92rem !important;
        font-weight: 500 !important;
        letter-spacing: -0.01em !important;
        color: rgba(255, 255, 255, 0.45) !important;
        background: transparent !important;
        border: none !important;
        border-radius: 9px !important;
        padding: 9px 20px !important;
        margin: 0 !important;
        transition: color 0.15s ease, background 0.15s ease;
        white-space: nowrap;
    }

    .stTabs [data-baseweb="tab"]:hover {
        color: rgba(255, 255, 255, 0.75) !important;
        background: rgba(255, 255, 255, 0.05) !important;
        box-shadow: none !important;
        transform: none !important;
    }

    .stTabs [aria-selected="true"] {
        color: #1a1a1a !important;
        background: #ffffff !important;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25), 0 0 0 0.5px rgba(0,0,0,0.08) !important;
    }

    /* Remove Streamlit's default blue underline indicator */
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
    }

    /* === Global interaction system: consistent hover and focus states === */
    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button,
    .stFileUploader label,
    [data-testid="stExpander"] details,
    .console-metric,
    .mini-panel,
    .console-panel {
        transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease, background-color 0.18s ease;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover,
    .stFormSubmitButton > button:hover,
    .stFileUploader label:hover,
    [data-testid="stExpander"] details:hover,
    .console-metric:hover,
    .mini-panel:hover {
        border-color: rgba(125, 183, 255, 0.46) !important;
        box-shadow: 0 0 0 1px rgba(125, 183, 255, 0.22), 0 10px 24px rgba(0, 0, 0, 0.16);
        transform: translateY(-1px);
    }

    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        border-radius: 24px !important;
        padding: 10px 20px !important;
        font-weight: 600;
    }

    /* Primary button: Green (Betsson 2025) */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button {
        background: var(--bs-primary) !important;
        color: #ffffff !important;
        border: none !important;
    }

    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover {
        background: #00933a !important;
        box-shadow: 0 8px 16px rgba(0, 166, 81, 0.3) !important;
    }

    .stButton > button[kind="primary"]:active,
    .stFormSubmitButton > button:active {
        background: #007a2d !important;
    }

    /* Secondary button: Orange variant */
    .stDownloadButton > button {
        background: var(--rc-brand) !important;
        color: #ffffff !important;
        border: none !important;
    }

    .stDownloadButton > button:hover {
        background: #E45D1C !important;
        box-shadow: 0 8px 16px rgba(255, 102, 0, 0.3) !important;
    }

    .stTextInput input:hover,
    .stTextArea textarea:hover,
    .stNumberInput input:hover,
    .stDateInput input:hover,
    div[data-baseweb="select"]:hover {
        border-color: rgba(125, 183, 255, 0.46) !important;
    }

    .stTextInput input:focus,
    .stTextArea textarea:focus,
    .stNumberInput input:focus,
    .stDateInput input:focus,
    .stButton > button:focus,
    .stDownloadButton > button:focus,
    .stFormSubmitButton > button:focus,
    .stTabs [data-baseweb="tab"]:focus,
    .stTabs [data-baseweb="tab"]:focus-visible,
    [data-testid="stExpander"] summary:focus,
    [data-testid="stExpander"] summary:focus-visible,
    [data-baseweb="select"]:focus-within {
        outline: none !important;
        border-color: rgba(125, 183, 255, 0.62) !important;
        box-shadow: 0 0 0 3px rgba(125, 183, 255, 0.26) !important;
    }

    .stMarkdown a {
        transition: color 0.16s ease, text-shadow 0.16s ease;
    }

    .stMarkdown a:hover {
        color: #9cc8ff;
        text-shadow: 0 0 12px rgba(125, 183, 255, 0.3);
    }

    .stMarkdown a:focus,
    .stMarkdown a:focus-visible {
        outline: none;
        border-radius: 4px;
        box-shadow: 0 0 0 3px rgba(125, 183, 255, 0.3);
    }

    @media (prefers-reduced-motion: reduce) {
        .stButton > button,
        .stDownloadButton > button,
        .stFormSubmitButton > button,
        .stFileUploader label,
        [data-testid="stExpander"] details,
        .stTabs [data-baseweb="tab"],
        .console-metric,
        .mini-panel,
        .console-panel,
        .stMarkdown a {
            transition: none !important;
            transform: none !important;
        }
    }

    @media (max-width: 900px) {
        .console-strip, .panel-grid {
            grid-template-columns: 1fr;
        }
    }
</style>
""", unsafe_allow_html=True)


def render_review_console_hero() -> None:
    """Render a compact session hero for the app shell."""
    document_name = st.session_state.get("document_name", "No document loaded")
    offer_key = st.session_state.get("offer_key", "Awaiting configuration")
    language_count = len(st.session_state.get("parsed_docs", []))
    variants = st.session_state.get("variants", [])
    variant_label = ", ".join(variants[:4]) if variants else "None"
    if len(variants) > 4:
        variant_label += f" (+{len(variants) - 4})"

    st.markdown(
        (
            "<section class='review-hero'>"
            "<div class='review-hero-head'>"
            f"<img class='review-hero-logo' src='{BETSSON_LOGO_URL}' alt='Betsson logo'/>"
            "<h1>CMS Template Generator</h1>"
            "</div>"
            "<p>Review console for localized campaign content, QA resolution, and export auditing.</p>"
            "<div class='hero-meta'>"
            f"<span class='hero-pill'><span class='label'>Document</span><strong>{html.escape(document_name)}</strong></span>"
            f"<span class='hero-pill'><span class='label'>Offer</span><strong>{html.escape(offer_key)}</strong></span>"
            f"<span class='hero-pill'><span class='label'>Languages</span><strong>{language_count}</strong></span>"
            f"<span class='hero-pill'><span class='label'>Variants</span><strong>{html.escape(variant_label)}</strong></span>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def render_console_metrics(readiness: dict, resolved_events: list[str]) -> None:
    """Render review-console QA strip."""
    resolved_count = len(resolved_events)
    mismatch_count = readiness.get("mismatch_count", 0)
    resolved_text = " | ".join(resolved_events[-2:]) if resolved_events else "No resolutions yet"
    toggle_key = "qa_issue_type_filter"
    if toggle_key not in st.session_state:
        st.session_state[toggle_key] = None

    cols = st.columns(5)

    with cols[0]:
        if st.button(
            f"READY\n{readiness['ready_count']}",
            key="metric_ready",
            type="secondary",
            width="stretch",
        ):
            st.session_state[toggle_key] = "ready" if st.session_state[toggle_key] != "ready" else None
            st.rerun()

    with cols[1]:
        if st.button(
            f"MISSING\n{readiness['missing_count']}",
            key="metric_missing",
            type="secondary",
            width="stretch",
        ):
            st.session_state[toggle_key] = "missing" if st.session_state[toggle_key] != "missing" else None
            st.rerun()

    with cols[2]:
        if st.button(
            f"INVALID\n{readiness['invalid_count']}",
            key="metric_invalid",
            type="secondary",
            width="stretch",
        ):
            st.session_state[toggle_key] = "invalid" if st.session_state[toggle_key] != "invalid" else None
            st.rerun()

    with cols[3]:
        tile_label = f"POTENTIAL WRONG LANGUAGE\n{mismatch_count}"
        if st.button(
            tile_label,
            key="qa_toggle_issue_actions_from_metric",
            type="secondary",
            disabled=mismatch_count == 0,
            width="stretch",
        ):
            st.session_state[toggle_key] = "mismatch" if st.session_state[toggle_key] != "mismatch" else None
            st.rerun()

    with cols[4]:
        st.button(
            f"RESOLVED\n{resolved_count}",
            key="metric_resolved",
            type="secondary",
            width="stretch",
        )


def render_issue_chips(readiness: dict, parsed_docs: list[ParsedDocument]) -> None:
    """Render clickable issue chips for direct language navigation."""
    filter_type = st.session_state.get("qa_issue_type_filter", None)
    if filter_type is None:
        return

    issue_buttons: list[tuple[str, str]] = []

    for doc in parsed_docs:
        lang = doc.language_code
        lang_name = LANGUAGE_NAMES.get(lang, lang)
        state = readiness["by_language"][lang]["status"]
        mismatch_info = readiness["by_language"][lang].get("language_mismatch", {})

        if filter_type == "mismatch" and mismatch_info.get("detected"):
            detected_lang = (mismatch_info.get("detected_lang") or "?").upper()
            issue_buttons.append((lang, f"🌐 {lang} {lang_name} (detected {detected_lang})"))
        elif filter_type == "missing" and state == "missing":
            issue_buttons.append((lang, f"⚠ {lang} {lang_name} (missing content)"))
        elif filter_type == "invalid" and state == "invalid":
            issue_buttons.append((lang, f"✖ {lang} {lang_name} (invalid placeholders)"))
        elif filter_type == "ready" and state == "ready":
            issue_buttons.append((lang, f"✓ {lang} {lang_name} (ready)"))

    if not issue_buttons:
        return

    st.markdown("<div class='chip-row'>", unsafe_allow_html=True)
    col_count = min(4, len(issue_buttons))
    cols = st.columns(col_count)
    for idx, (lang, label) in enumerate(issue_buttons):
        col = cols[idx % col_count]
        with col:
            if st.button(label, key=f"qa_chip_{lang}_{idx}", width="stretch", type="secondary"):
                st.session_state["qa_target_lang"] = lang
                st.session_state["qa_language_select"] = lang
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_language_mismatch_warnings(readiness: dict, parsed_docs: list[ParsedDocument]) -> None:
    """
    Render prominent banner for languages with detected mismatches (e.g., English content in Spanish doc).
    Provides quick action buttons to jump to affected languages.
    """
    # Extract languages with mismatches
    mismatch_langs: list[tuple[str, str]] = []
    for doc in parsed_docs:
        lang = doc.language_code
        lang_name = LANGUAGE_NAMES.get(lang, lang)
        mismatch_info = readiness["by_language"][lang].get("language_mismatch", {})
        if mismatch_info.get("detected"):
            detected = mismatch_info.get("detected_lang", "unknown").upper()
            mismatch_langs.append((lang, lang_name, detected))
    
    if not mismatch_langs:
        return  # No mismatches, don't show banner
    
    # Render banner with alert styling
    st.markdown(
        "<div style='background: linear-gradient(135deg, rgba(255,102,0,0.15), rgba(255,102,0,0.08)); "
        "border-left: 4px solid #FF6600; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px;'>"
        "<div style='display: flex; align-items: center; gap: 12px; margin-bottom: 12px;'>"
        "<span style='font-size: 20px;'>🌐</span>"
        "<div>"
        f"<strong style='color: #FF6600;'>Potential Language Mismatches Detected</strong>"
        "<p style='margin: 4px 0 0 0; font-size: 0.9em; color: #aaa;'>"
        "The tool detected content in a different language than the filename suggests. "
        "Review the languages below to ensure your documents are correctly translated."
        "</p></div></div>",
        unsafe_allow_html=True
    )
    
    # Quick action buttons
    st.markdown("<div style='display: flex; gap: 8px; flex-wrap: wrap;'>", unsafe_allow_html=True)
    for lang, lang_name, detected_lang in mismatch_langs:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(
                f"<span style='display: inline-block; padding: 6px 12px; "
                f"background: rgba(255,102,0,0.2); border-radius: 6px; font-size: 0.9em;'>"
                f"<strong>{lang}</strong> ({lang_name}) <br/>"
                f"<span style='color: #FF6600;'>Detected as: {detected_lang}</span>"
                f"</span>",
                unsafe_allow_html=True
            )
        with col2:
            if st.button("Review →", key=f"mismatch_quick_{lang}", help=f"Jump to {lang} language", width="stretch"):
                st.session_state["qa_target_lang"] = lang
                st.session_state["qa_language_select"] = lang
                st.rerun()
    
    st.markdown("</div>", unsafe_allow_html=True)


def render_console_section_header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        (
            "<div class='console-panel'>"
            f"<div class='section-kicker'>{html.escape(kicker)}</div>"
            f"<div class='console-panel-title'>{html.escape(title)}</div>"
            f"<p class='console-panel-subtitle'>{html.escape(subtitle)}</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def main():
    render_review_console_hero()
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙ Offer Configuration")
        st.caption("Set campaign parameters and communication payload before generation.")
        
        # Check for auto-detected values (set during upload processing)
        detected_task = st.session_state.get("detected_task_type")
        detected_reward = st.session_state.get("detected_reward_type")
        detected_image = st.session_state.get("detected_image")
        
        # Check if we just detected new values and need to apply them
        apply_detection = st.session_state.pop("apply_detection", False)

        with st.expander("Offer Setup", expanded=True):
            # Task Type - with custom option
            task_type_options = TASK_TYPES + ["➕ Custom..."]

            # Initialize or update widget key based on detection
            if apply_detection and detected_task and detected_task in task_type_options:
                st.session_state["task_type_select"] = detected_task
            elif "task_type_select" not in st.session_state:
                if detected_task and detected_task in task_type_options:
                    st.session_state["task_type_select"] = detected_task
                elif "PlaceBetWithSettlement" in task_type_options:
                    st.session_state["task_type_select"] = "PlaceBetWithSettlement"
                else:
                    st.session_state["task_type_select"] = task_type_options[0]

            task_type_selection = st.selectbox(
                "Task Type",
                options=task_type_options,
                key="task_type_select",
                help="The task type for this offer (used in template key and metadata)",
            )

            if detected_task and task_type_selection == detected_task:
                st.caption("🔍 Auto-detected")

            if task_type_selection == "➕ Custom...":
                task_type = st.text_input(
                    "Custom Task Type",
                    placeholder="e.g., SpinTheWheel",
                    help="Enter a new task type name (PascalCase, no spaces)",
                )
                if task_type:
                    st.caption(f"✅ Using custom: `{task_type}`")
            else:
                task_type = task_type_selection

            # Reward Type - with custom option
            reward_type_options = REWARD_TYPES + ["➕ Custom..."]
            if apply_detection and detected_reward and detected_reward in reward_type_options:
                st.session_state["reward_type_select"] = detected_reward
            elif "reward_type_select" not in st.session_state:
                if detected_reward and detected_reward in reward_type_options:
                    st.session_state["reward_type_select"] = detected_reward
                elif "CashFreespin" in reward_type_options:
                    st.session_state["reward_type_select"] = "CashFreespin"
                else:
                    st.session_state["reward_type_select"] = reward_type_options[0]

            reward_type_selection = st.selectbox(
                "Reward Type",
                options=reward_type_options,
                key="reward_type_select",
                help="The reward type for this offer",
            )

            if detected_reward and reward_type_selection == detected_reward:
                st.caption("🔍 Auto-detected")

            if reward_type_selection == "➕ Custom...":
                reward_type = st.text_input(
                    "Custom Reward Type",
                    placeholder="e.g., WheelSpin",
                    help="Enter a new reward type name (PascalCase, no spaces)",
                )
                if reward_type:
                    st.caption(f"✅ Using custom: `{reward_type}`")
            else:
                reward_type = reward_type_selection

            current_offer = f"{task_type}-{reward_type}" if task_type and reward_type else "Awaiting setup"
            st.caption(f"Offer key preview: {current_offer}")

            use_bonus_product = st.checkbox("Include Bonus Product", value=False)
            bonus_product = None
            if use_bonus_product:
                bonus_product_options = BONUS_PRODUCTS + ["➕ Custom..."]
                bonus_product_selection = st.selectbox(
                    "Bonus Product",
                    options=bonus_product_options,
                    help="Optional product specification",
                )
                if bonus_product_selection == "➕ Custom...":
                    bonus_product = st.text_input(
                        "Custom Bonus Product",
                        placeholder="e.g., NewProduct",
                    )
                else:
                    bonus_product = bonus_product_selection

        with st.expander("OMS Image", expanded=True):
            st.caption("Select the visual used in OMS previews and generated templates.")
            image_options = list(OMS_IMAGES.keys())
            if apply_detection and detected_image and detected_image in image_options:
                st.session_state["image_select"] = detected_image
            elif "image_select" not in st.session_state:
                if detected_image and detected_image in image_options:
                    st.session_state["image_select"] = detected_image
                else:
                    st.session_state["image_select"] = image_options[0]

            selected_image_display = st.selectbox(
                "Select OMS Image",
                options=image_options,
                key="image_select",
                help="Brand-agnostic image from CMS GenericSiteMessageImageRepository",
                format_func=format_oms_image_option,
            )

            if detected_image and selected_image_display == detected_image:
                st.caption("🔍 Auto-selected based on reward type")

            image_tuple = OMS_IMAGES.get(selected_image_display, ("CW_BonusFreeSpin_casino", "3736707", "6f9506db0ced4118993357b114c831ce.jpg"))
            selected_image_key = image_tuple[0]
            selected_image_id = image_tuple[1]
            selected_image_file = image_tuple[2] if len(image_tuple) > 2 else None
            selected_image_tags = infer_oms_image_tags(selected_image_display, selected_image_key)

            if selected_image_file:
                image_path = Path(__file__).parent / "images" / selected_image_file
                if image_path.exists():
                    st.image(str(image_path), caption=selected_image_display, width=150)
            if selected_image_tags:
                st.caption(f"Tags: {' • '.join(selected_image_tags)}")
            st.caption(f"CMS Key: `{selected_image_key}` | ID: `{selected_image_id}`")

        with st.expander("Send Conditions", expanded=False):
            st.caption("Toggle message triggers included in export payload.")
            default_conditions = {
                "NotOptedIn",
                "JoinedCampaign",
                "CampaignHasStarted",
                "ClaimedReward-TemplateA",
                "ClaimedReward-TemplateB",
            }
            selected_conditions = []
            for condition in SEND_CONDITIONS:
                if st.checkbox(condition, value=condition in default_conditions):
                    selected_conditions.append(condition)

            custom_condition = st.text_input(
                "Custom Send Condition (optional)",
                placeholder="e.g., TaskCompleted",
                help="Add a new send condition if needed",
            )
            if custom_condition:
                selected_conditions.append(custom_condition)
                st.caption(f"✅ Added: `{custom_condition}`")

        st.markdown("### Configuration Health")
        
        # Validation
        config_valid = True
        if not task_type:
            st.warning("⚠️ Please enter a Task Type")
            config_valid = False
        if not reward_type:
            st.warning("⚠️ Please enter a Reward Type")
            config_valid = False
        
        # Generate offer key (bonus_product goes in metadata only, not in key)
        if task_type and reward_type:
            offer_key = f"{task_type}-{reward_type}"
            st.markdown(
                f"<div class='sidebar-status-wrap'><div class='sidebar-status-pill ok'><strong>Offer Key:</strong> {html.escape(offer_key)}</div></div>",
                unsafe_allow_html=True,
            )
        else:
            offer_key = ""
            st.markdown(
                "<div class='sidebar-status-wrap'><div class='sidebar-status-pill warn'>Task Type and Reward Type are required to generate an offer key.</div></div>",
                unsafe_allow_html=True,
            )
    
    # Main content area
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Upload", "Review", "Export", "Compare", "Help"])
    
    with tab1:
        st.header("Step 1: Upload Content")
        
        st.subheader("📄 Localized Content (Word Docs)")
        uploaded_file = st.file_uploader(
            "Upload ZIP with Word documents",
            type=["zip"],
            help="ZIP containing {LANGUAGE}_{OfferName}.docx files",
            key="content_zip",
        )
        
        st.divider()
        
        if uploaded_file:
            with st.spinner("Extracting and parsing documents..."):
                current_upload_key = f"{uploaded_file.name}:{uploaded_file.size}"
                previous_upload_key = st.session_state.get("upload_file_key")
                is_new_upload = previous_upload_key != current_upload_key

                if not is_new_upload and "parsed_docs" in st.session_state:
                    parsed_docs = st.session_state["parsed_docs"]
                    detection = st.session_state.get("auto_detection", detect_offer_type(parsed_docs))
                    detected_variants = set(st.session_state.get("variants", []))
                    auto_task = detection.get("task_type")
                    auto_reward = detection.get("reward_type")
                    auto_image = detection.get("recommended_image")
                else:
                    # Extract ZIP to temp directory
                    temp_dir = Path(tempfile.mkdtemp())
                    
                    try:
                        with zipfile.ZipFile(uploaded_file, "r") as zip_ref:
                            zip_ref.extractall(temp_dir)
                        
                        # Find the folder with Word docs (might be nested)
                        docx_files = list(temp_dir.rglob("*.docx"))
                        if not docx_files:
                            st.error("No Word documents found in ZIP")
                            return

                        # Use the parent folder of the first docx
                        docs_folder = docx_files[0].parent
                        
                        # Parse all documents
                        parsed_docs = parse_documents_from_folder(docs_folder)
                        
                        # Auto-detect variants from parsed templates
                        detected_variants = set()
                        for doc in parsed_docs:
                            if doc.launch_oms:
                                for t in doc.launch_oms.templates:
                                    detected_variants.add(t.variant)
                            if doc.reminder_oms:
                                for t in doc.reminder_oms.templates:
                                    detected_variants.add(t.variant)
                            if doc.reward_oms:
                                for t in doc.reward_oms.templates:
                                    detected_variants.add(t.variant)
                            if doc.launch_sms:
                                for t in doc.launch_sms.templates:
                                    detected_variants.add(t.variant)
                            if doc.reminder_sms:
                                for t in doc.reminder_sms.templates:
                                    detected_variants.add(t.variant)
                        
                        # Auto-detect offer type from content
                        detection = detect_offer_type(parsed_docs)
                        st.session_state["auto_detection"] = detection
                        
                        # Use detected values if available and user hasn't manually set them
                        auto_task = detection.get("task_type")
                        auto_reward = detection.get("reward_type")
                        auto_image = detection.get("recommended_image")
                    finally:
                        shutil.rmtree(temp_dir, ignore_errors=True)

                    st.session_state["parsed_docs"] = parsed_docs
                    if is_new_upload or "original_parsed_docs" not in st.session_state:
                        st.session_state["original_parsed_docs"] = copy.deepcopy(parsed_docs)
                    st.session_state["document_name"] = uploaded_file.name
                    if is_new_upload or "upload_timestamp" not in st.session_state:
                        st.session_state["upload_timestamp"] = datetime.now()
                    if is_new_upload or "qa_fixes_applied" not in st.session_state:
                        st.session_state["qa_fixes_applied"] = {}
                    if is_new_upload or "qa_fix_details" not in st.session_state:
                        st.session_state["qa_fix_details"] = {}
                    if is_new_upload or "qa_content_edit_events" not in st.session_state:
                        st.session_state["qa_content_edit_events"] = []
                        if is_new_upload or "qa_fix_events" not in st.session_state:
                            st.session_state["qa_fix_events"] = []
                        if is_new_upload or "editor_values" not in st.session_state:
                            st.session_state["editor_values"] = {}
                    st.session_state["upload_file_key"] = current_upload_key

                st.session_state["offer_key"] = offer_key
                st.session_state["task_type"] = task_type
                st.session_state["reward_type"] = reward_type
                st.session_state["bonus_product"] = bonus_product
                st.session_state["send_conditions"] = selected_conditions
                st.session_state["variants"] = sorted(detected_variants)
                st.session_state["image_key"] = selected_image_key
                st.session_state["image_id"] = selected_image_id
                st.session_state["image_file"] = selected_image_file
                st.session_state["image_display"] = selected_image_display

                st.success(f"✅ Parsed {len(parsed_docs)} documents")

                # Auto-apply detection results immediately (no button needed)
                if auto_task or auto_reward or auto_image:
                    # Check if these are new values that need a rerun
                    needs_rerun = (
                        (auto_task and st.session_state.get("detected_task_type") != auto_task) or
                        (auto_reward and st.session_state.get("detected_reward_type") != auto_reward) or
                        (auto_image and st.session_state.get("detected_image") != auto_image)
                    )

                    # Set detected values in session state
                    if auto_task:
                        st.session_state["detected_task_type"] = auto_task
                    if auto_reward:
                        st.session_state["detected_reward_type"] = auto_reward
                    if auto_image:
                        st.session_state["detected_image"] = auto_image

                    # Rerun to apply - set flag so sidebar knows to update widget values
                    if needs_rerun:
                        st.session_state["apply_detection"] = True
                        st.rerun()

                    # Show what was auto-detected as confirmation
                    st.info("🔍 **Auto-Detected & Applied**")
                    det_col1, det_col2, det_col3 = st.columns(3)
                    with det_col1:
                        if auto_task:
                            conf_icon = "🎯" if detection["task_confidence"] == "high" else "🤔"
                            st.markdown(f"**Task Type:** {conf_icon} `{auto_task}`")
                            st.caption(f"Confidence: {detection['task_confidence']}")
                    with det_col2:
                        if auto_reward:
                            conf_icon = "🎯" if detection["reward_confidence"] == "high" else "🤔"
                            st.markdown(f"**Reward Type:** {conf_icon} `{auto_reward}`")
                            st.caption(f"Confidence: {detection['reward_confidence']}")
                    with det_col3:
                        if auto_image:
                            st.markdown(f"**Suggested Image:** `{auto_image}`")
                    st.caption("*Values applied to sidebar. You can override them if needed.*")

                # Quality Reports Section
                st.markdown("### 🔍 Quality Reports")

                report_col1, report_col2 = st.columns(2)

                with report_col1:
                    # Template Consistency Check
                    st.markdown("**Template Consistency**")
                    consistency = check_template_consistency(parsed_docs)
                    if consistency["is_consistent"]:
                        st.success("✅ All languages have consistent template variants")
                    else:
                        st.error(f"❌ Inconsistencies found ({len(consistency['issues'])} issues)")
                        with st.expander("View consistency issues"):
                            for issue in consistency["issues"]:
                                st.write(issue)

                with report_col2:
                    # Missing Content Report
                    st.markdown("**Content Completeness**")
                    missing_report = generate_missing_content_report(parsed_docs)

                    if missing_report["total_issues"] == 0:
                        st.success("✅ All content is complete")
                    else:
                        languages_with_issues = len([l for l, i in missing_report["by_language"].items() if i])
                        st.warning(f"⚠️ {missing_report['total_issues']} issues in {languages_with_issues} languages")
                        with st.expander("View missing content details"):
                            for lang, issues in missing_report["by_language"].items():
                                if issues:
                                    st.markdown(f"**{lang}:**")
                                    for issue in issues:
                                        st.write(f"  {issue}")

                # Show summary table with expanded language names
                st.markdown("### 📋 Languages Parsed")
                summary_data = []
                for doc in parsed_docs:
                    lang_name = LANGUAGE_NAMES.get(doc.language_code, doc.language_code)
                    cms_markets = LANGUAGE_MAPPING.get(doc.language_code, [doc.language_code.lower()])
                    sms_count = (len(doc.launch_sms.templates) if doc.launch_sms else 0) + \
                               (len(doc.reminder_sms.templates) if doc.reminder_sms else 0)
                    summary_data.append({
                        "Language": f"{doc.language_code} ({lang_name})",
                        "CMS Markets": ", ".join(cms_markets),
                        "OMS Templates": len(doc.launch_oms.templates) if doc.launch_oms else 0,
                        "SMS Templates": sms_count,
                        "Has T&Cs": "✅" if doc.tc else "❌",
                    })

                # Calculate height to show all rows without scrolling
                # Each row ~35px + header ~40px + padding
                table_height = 40 + (len(summary_data) * 35) + 10
                st.dataframe(
                    pd.DataFrame(summary_data),
                    width="stretch",
                    height=table_height,
                    hide_index=True
                )
                    
    
    with tab2:
        render_console_section_header(
            "QA Review",
            "Preview Extracted Content",
            "Review content by language, resolve placeholder issues, and prepare the package for export.",
        )
        
        if "parsed_docs" not in st.session_state:
            st.markdown("""
            <div class='empty-state'>
                <div class='empty-state-icon'>👁️</div>
                <p class='empty-state-title'>No Content to Preview</p>
                <p class='empty-state-body'>Upload a ZIP file with your localized Word documents on the Upload tab to start reviewing content here.</p>
                <span class='empty-state-hint'>← Go to Upload Content</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            parsed_docs = st.session_state["parsed_docs"]
            effective_docs = build_effective_parsed_docs(parsed_docs)

            readiness = build_language_readiness(effective_docs)

            status_by_lang = {
                doc.language_code: readiness["by_language"][doc.language_code]["status"]
                for doc in parsed_docs
            }
            previous_status_by_lang = st.session_state.get("qa_prev_status_by_lang", {})
            newly_resolved = collect_resolved_status_transitions(previous_status_by_lang, status_by_lang)
            if newly_resolved:
                resolved_events = st.session_state.get("qa_resolved_events", [])
                for event in newly_resolved:
                    if event not in resolved_events:
                        resolved_events.append(event)
                st.session_state["qa_resolved_events"] = resolved_events[-6:]
            st.session_state["qa_prev_status_by_lang"] = status_by_lang

            resolved_events = st.session_state.get("qa_resolved_events", [])
            render_console_metrics(readiness, resolved_events)

            issue_langs = [lang for lang, status in status_by_lang.items() if status != "ready"]
            render_issue_chips(readiness, parsed_docs)

            if readiness["has_issues"]:
                st.caption("Click an issue chip to jump directly to that language.")
            else:
                st.caption("All languages are currently clear for export.")

            show_qa_details = st.toggle(
                "Show QA details",
                value=False,
                help="Expanded details for each language status.",
            )

            if show_qa_details:
                rows = []
                for doc in parsed_docs:
                    lang = doc.language_code
                    lang_name = LANGUAGE_NAMES.get(lang, lang)
                    state = readiness["by_language"][lang]["status"]
                    status_label = "✅ Ready" if state == "ready" else ("⚠️ Missing" if state == "missing" else "❌ Invalid")
                    
                    # Check for language mismatch
                    mismatch_info = readiness["by_language"][lang].get("language_mismatch", {})
                    mismatch_label = ""
                    if mismatch_info.get("detected"):
                        detected = mismatch_info.get("detected_lang", "unknown").upper()
                        mismatch_label = f"🌐 Detected as {detected}"
                    else:
                        mismatch_label = "✓"
                    
                    rows.append({
                        "Language": f"{lang} ({lang_name})",
                        "Status": status_label,
                        "Invalid placeholders": readiness["by_language"][lang]["invalid_count"],
                        "Missing issues": len(readiness["by_language"][lang]["missing_issues"]),
                        "Language Match": mismatch_label,
                    })

                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=210)
            
            # Language selector with full names
            languages = [doc.language_code for doc in parsed_docs]
            
            def format_language(code: str) -> str:
                """Format language code with full name."""
                name = LANGUAGE_NAMES.get(code, code)
                return f"{code} - {name}"
            
            if "qa_language_select" not in st.session_state or st.session_state.get("qa_language_select") not in languages:
                st.session_state["qa_language_select"] = issue_langs[0] if issue_langs else (languages[0] if languages else None)

            default_lang = st.session_state.get("qa_target_lang")
            if default_lang and default_lang in languages:
                st.session_state["qa_language_select"] = default_lang
                del st.session_state["qa_target_lang"]

            if st.session_state.get("qa_advance_after_fix"):
                current_lang = st.session_state.get("qa_language_select", st.session_state.get("qa_last_selected_lang", ""))
                if current_lang in issue_langs:
                    st.session_state["qa_language_select"] = current_lang
                else:
                    st.session_state["qa_language_select"] = choose_next_issue_language(current_lang, issue_langs) or current_lang
                st.session_state["qa_advance_after_fix"] = False

            selected_lang = st.selectbox(
                "Select Language to Preview",
                languages,
                format_func=format_language,
                key="qa_language_select",
            )

            previous_selected_lang = st.session_state.get("qa_last_selected_lang")
            if previous_selected_lang and previous_selected_lang != selected_lang:
                st.session_state.pop("qa_last_fix_summary", None)

            st.session_state["qa_last_selected_lang"] = selected_lang
            
            selected_doc = next((d for d in parsed_docs if d.language_code == selected_lang), None)
            selected_mismatch_info = readiness["by_language"].get(selected_lang, {}).get("language_mismatch", {})
            selected_lang_has_mismatch = bool(selected_mismatch_info.get("detected"))
            
            if selected_doc:
                available_safe_fixes = count_safe_fixes_for_language(selected_lang, selected_doc)
                if available_safe_fixes > 0:
                    fix_col, summary_col = st.columns([2, 10])
                    with fix_col:
                        if st.button(
                            f"Fix safe in {selected_lang}",
                            key=f"fix_all_safe_{selected_lang}",
                            width="stretch",
                            type="secondary",
                            help="Apply high-confidence placeholder fixes across SMS/OMS/T&C in this language.",
                        ):
                            changes = apply_safe_fixes_for_language(selected_lang, selected_doc)
                            if changes:
                                # Stay on current language, don't jump
                                history = st.session_state.get("qa_fix_history", [])
                                history.append(f"{selected_lang}: " + ", ".join(changes[:4]))
                                st.session_state["qa_fix_history"] = history[-8:]
                                st.session_state["qa_last_fix_summary"] = (
                                    f"✅ Applied safe fixes in {selected_lang}: " + ", ".join(changes[:5])
                                )
                                st.rerun()
                            else:
                                st.session_state["qa_last_fix_summary"] = (
                                    f"No high-confidence placeholder fixes found for {selected_lang}."
                                )
                                st.rerun()

                    with summary_col:
                        st.caption(
                            f"{available_safe_fixes} safe fixable field(s). "
                            "Applies only high-confidence fixes. Use per-field Undo if needed."
                        )

                if "qa_last_fix_summary" in st.session_state:
                    st.caption(st.session_state["qa_last_fix_summary"])

                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📱 SMS Templates")
                    all_sms_templates = []
                    if selected_doc.launch_sms:
                        for t in selected_doc.launch_sms.templates:
                            all_sms_templates.append(("Launch", t))
                    if selected_doc.reminder_sms:
                        for t in selected_doc.reminder_sms.templates:
                            all_sms_templates.append(("Reminder", t))
                    
                    if all_sms_templates:
                        for idx, (sms_type, template) in enumerate(all_sms_templates):
                            sms_body = template.body or ""
                            sms_key = f"sms_{selected_lang}_{idx}_{sms_type}_{template.variant}"
                            sms_fix_buffer = f"fix_buffer_{sms_key}"
                            sms_effective = st.session_state.get(sms_fix_buffer, st.session_state.get(sms_key, sms_body))

                            char_count, color, char_msg = get_sms_char_info(sms_effective)
                            invalid_placeholders = validate_placeholders(sms_effective)
                            missing = check_missing_content("SMS", body=sms_effective)

                            sms_flags: list[str] = []
                            if invalid_placeholders:
                                sms_flags.append("✖")  # Placeholder problems
                            if missing:
                                sms_flags.append("⚠")  # Missing required content
                            if color in {"orange", "red"}:
                                sms_flags.append("📏")  # SMS length segment risk
                            if not sms_flags:
                                sms_flags.append("✅")
                            if selected_lang_has_mismatch:
                                sms_flags.append("🌐")  # Language review required

                            expander_label = f"{' '.join(sms_flags)} {sms_type} - Template {template.variant} ({template.send_condition})"
                            
                            with st.expander(expander_label):
                                fix_buffer_key = f"fix_buffer_{sms_key}"
                                sync_fix_buffer_to_widget(sms_key, sms_body)
                                edited_body = st.text_area("Body", height=100, key=sms_key)
                                set_editor_value(sms_key, edited_body)
                                
                                _, color, char_msg = get_sms_char_info(edited_body)
                                if color == "green":
                                    st.success(char_msg)
                                elif color == "orange":
                                    st.warning(char_msg)
                                elif color == "red":
                                    st.error(char_msg)
                                else:
                                    st.info(char_msg)
                                
                                invalid = validate_placeholders(edited_body)
                                if invalid:
                                    render_invalid_placeholder_assistant(
                                        field_label="Body",
                                        text=edited_body,
                                        fix_buffer_key=fix_buffer_key,
                                        button_key=f"fix_{sms_key}",
                                        language_code=selected_lang,
                                        tracking_field_label=f"SMS {sms_type} {template.variant} Body",
                                    )
                                
                                for warn in check_missing_content("SMS", body=edited_body):
                                    st.warning(warn)
                    else:
                        st.warning("No SMS templates found")
                
                with col2:
                    st.subheader("📧 OMS Templates")
                    
                    # Collect all OMS templates: Launch, Reminder, Reward
                    all_oms_templates = []
                    if selected_doc.launch_oms:
                        for t in selected_doc.launch_oms.templates:
                            all_oms_templates.append(("Launch", t))
                    if selected_doc.reminder_oms:
                        for t in selected_doc.reminder_oms.templates:
                            all_oms_templates.append(("Reminder", t))
                    if selected_doc.reward_oms:
                        for t in selected_doc.reward_oms.templates:
                            all_oms_templates.append(("Reward", t))
                    
                    if all_oms_templates:
                        for idx, (oms_type, template) in enumerate(all_oms_templates):
                            oms_title = template.title or ""
                            oms_body = template.body or ""
                            oms_cta = template.cta or ""

                            title_key = f"oms_title_{selected_lang}_{idx}_{oms_type}_{template.variant}"
                            body_key = f"oms_body_{selected_lang}_{idx}_{oms_type}_{template.variant}"
                            cta_key = f"oms_cta_{selected_lang}_{idx}_{oms_type}_{template.variant}"
                            title_fix_buffer = f"fix_buffer_{title_key}"
                            body_fix_buffer = f"fix_buffer_{body_key}"
                            cta_fix_buffer = f"fix_buffer_{cta_key}"

                            effective_title = st.session_state.get(title_fix_buffer, st.session_state.get(title_key, oms_title))
                            effective_body = st.session_state.get(body_fix_buffer, st.session_state.get(body_key, oms_body))
                            effective_cta = st.session_state.get(cta_fix_buffer, st.session_state.get(cta_key, oms_cta))
                            
                            all_text = effective_title + " " + effective_body + " " + effective_cta
                            invalid_placeholders = validate_placeholders(all_text)
                            missing = check_missing_content("OMS", title=effective_title, body=effective_body, cta=effective_cta)

                            oms_flags: list[str] = []
                            if invalid_placeholders:
                                oms_flags.append("✖")
                            if missing:
                                oms_flags.append("⚠")
                            if not oms_flags:
                                oms_flags.append("✅")
                            if selected_lang_has_mismatch:
                                oms_flags.append("🌐")

                            expander_label = f"{' '.join(oms_flags)} {oms_type} - Template {template.variant} ({template.send_condition})"
                            
                            with st.expander(expander_label):
                                sync_fix_buffer_to_widget(title_key, oms_title)
                                sync_fix_buffer_to_widget(body_key, oms_body)
                                sync_fix_buffer_to_widget(cta_key, oms_cta)
                                
                                edited_title = st.text_input("Title", key=title_key)
                                edited_body = st.text_area("Body (BBCode)", height=150, key=body_key)
                                edited_cta = st.text_input("CTA", key=cta_key)
                                set_editor_value(title_key, edited_title)
                                set_editor_value(body_key, edited_body)
                                set_editor_value(cta_key, edited_cta)

                                title_invalid = validate_placeholders(edited_title)
                                if title_invalid:
                                    render_invalid_placeholder_assistant(
                                        field_label="Title",
                                        text=edited_title,
                                        fix_buffer_key=title_fix_buffer,
                                        button_key=f"fix_{title_key}",
                                        language_code=selected_lang,
                                        tracking_field_label=f"OMS {oms_type} {template.variant} Title",
                                    )

                                body_invalid = validate_placeholders(edited_body)
                                if body_invalid:
                                    render_invalid_placeholder_assistant(
                                        field_label="Body",
                                        text=edited_body,
                                        fix_buffer_key=body_fix_buffer,
                                        button_key=f"fix_{body_key}",
                                        language_code=selected_lang,
                                        tracking_field_label=f"OMS {oms_type} {template.variant} Body",
                                    )

                                cta_invalid = validate_placeholders(edited_cta)
                                if cta_invalid:
                                    render_invalid_placeholder_assistant(
                                        field_label="CTA",
                                        text=edited_cta,
                                        fix_buffer_key=cta_fix_buffer,
                                        button_key=f"fix_{cta_key}",
                                        language_code=selected_lang,
                                        tracking_field_label=f"OMS {oms_type} {template.variant} CTA",
                                    )

                                all_edited = edited_title + " " + edited_body + " " + edited_cta
                                placeholder_stats = analyze_placeholders(all_edited)

                                health_col, toggle_col = st.columns([3, 2])
                                with health_col:
                                    st.caption(
                                        f"Placeholder Health: "
                                        f"Total {placeholder_stats['total']} | "
                                        f"Valid {placeholder_stats['valid']} | "
                                        f"Invalid {placeholder_stats['invalid']}"
                                    )

                                raw_mode_key = f"oms_raw_mode_{selected_lang}_{idx}_{oms_type}_{template.variant}"
                                with toggle_col:
                                    show_raw_placeholders = st.toggle(
                                        "Show raw placeholders",
                                        value=False,
                                        key=raw_mode_key,
                                        help="When enabled, valid placeholders are shown as raw %%placeholder%% tokens. When disabled, valid placeholders render as realistic sample values.",
                                    )

                                if placeholder_stats["invalid"] > 0:
                                    with st.expander("Placeholder details", expanded=False):
                                        if placeholder_stats["invalid"] > 0:
                                            invalid_labels = [f"%%{token}%%" for token in placeholder_stats["invalid_tokens"]]
                                            st.caption("Invalid placeholders: " + ", ".join(invalid_labels))
                                
                                if edited_body:
                                    st.markdown("**Desktop OMS Preview:**")
                                    if show_raw_placeholders:
                                        st.caption("Legend: Amber = available placeholder, Red = not available in Campaign Wizard")
                                    else:
                                        st.caption("Realistic mode: Green = sample value for valid placeholder, Red = invalid placeholder")
                                    image_data_uri = ""
                                    if selected_image_file:
                                        image_path = Path(__file__).parent / "images" / selected_image_file
                                        image_data_uri = image_file_to_data_uri(image_path)

                                    oms_card_html = render_oms_desktop_preview(
                                        title=edited_title,
                                        body=edited_body,
                                        cta=edited_cta,
                                        image_data_uri=image_data_uri,
                                        placeholder_mode="raw" if show_raw_placeholders else "realistic",
                                    )
                                    components.html(oms_card_html, height=430, scrolling=True)

                                invalid = validate_placeholders(all_edited)
                                
                                for warn in check_missing_content("OMS", title=edited_title, body=edited_body, cta=edited_cta):
                                    st.warning(warn)
                    else:
                        st.warning("No OMS templates found")
                
                # Terms & Conditions - full width below columns
                st.subheader("📋 Terms & Conditions")
                if selected_doc.tc:
                    tc_sig = selected_doc.tc.significant_terms or ""
                    tc_full = selected_doc.tc.terms_and_conditions or ""
                    
                    # Pre-initialize widget keys so we can check edited values
                    sig_key = f"tc_sig_{selected_lang}"
                    full_key = f"tc_full_{selected_lang}"
                    sig_fix_buffer = f"fix_buffer_{sig_key}"
                    full_fix_buffer = f"fix_buffer_{full_key}"
                    sync_fix_buffer_to_widget(sig_key, tc_sig)
                    sync_fix_buffer_to_widget(full_key, tc_full)
                    
                    # Get EDITED values from session state (not original template)
                    edited_tc_sig = get_effective_widget_value(sig_key, tc_sig)
                    edited_tc_full = get_effective_widget_value(full_key, tc_full)
                    
                    # Check issues based on EDITED values
                    all_tc_text = edited_tc_sig + " " + edited_tc_full
                    invalid_tc = validate_placeholders(all_tc_text)
                    tc_missing = []
                    if not edited_tc_sig.strip():
                        tc_missing.append("Significant Terms empty")
                    if not edited_tc_full.strip():
                        tc_missing.append("Full T&Cs empty")
                    
                    if invalid_tc or tc_missing:
                        st.warning(f"⚠️ Issues found: {', '.join(tc_missing) if tc_missing else ''} {', '.join(['Invalid: %%' + p + '%%' for p in invalid_tc]) if invalid_tc else ''}")
                    
                    tc_col1, tc_col2 = st.columns(2)
                    with tc_col1:
                        edited_sig = st.text_area("Significant Terms", height=200, key=sig_key)
                        set_editor_value(sig_key, edited_sig)
                        sig_invalid = validate_placeholders(edited_sig)
                        if sig_invalid:
                                icon = "⚠️" if sig_invalid else "✅"
                                render_invalid_placeholder_assistant(
                                    field_label=f"{icon} Significant Terms",
                                button_key=f"fix_{sig_key}",
                                language_code=selected_lang,
                                tracking_field_label="T&C Significant Terms",
                            )
                        if not edited_sig.strip():
                            st.warning("⚠️ Significant Terms is empty")
                            
                    with tc_col2:
                        edited_full = st.text_area("Full Terms & Conditions", height=200, key=full_key)
                        set_editor_value(full_key, edited_full)
                        full_invalid = validate_placeholders(edited_full)
                        if full_invalid:
                            icon = "⚠️" if full_invalid else "✅"
                            render_invalid_placeholder_assistant(
                                field_label=f"{icon} Full T&Cs",
                                text=edited_full,
                                fix_buffer_key=full_fix_buffer,
                                button_key=f"fix_{full_key}",
                                language_code=selected_lang,
                                tracking_field_label="T&C Full Terms",
                            )
                        if not edited_full.strip():
                            st.warning("⚠️ Full T&Cs is empty")
                else:
                    st.warning("No T&Cs found")
    
    with tab3:
        render_console_section_header(
            "Release Gate",
            "Generate CMS Packages",
            "Validate export readiness, capture audit context, and produce final CMS packages.",
        )
        
        if "parsed_docs" not in st.session_state:
            st.markdown("""
            <div class='empty-state'>
                <div class='empty-state-icon'>📥</div>
                <p class='empty-state-title'>Ready to Generate</p>
                <p class='empty-state-body'>Upload and parse your localized documents first. Once done, come back here to validate and export your CMS packages.</p>
                <span class='empty-state-hint'>← Upload documents to unlock this step</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            parsed_docs = st.session_state.get("parsed_docs", [])
            effective_docs = build_effective_parsed_docs(parsed_docs)
            
            send_conditions_label = ", ".join(st.session_state.get("send_conditions", [])) or "None"
            variants_label = ", ".join(st.session_state.get("variants", [])) or "None"
            st.markdown(
                (
                    "<div class='console-panel'>"
                    "<span class='section-kicker'>CONFIGURATION</span>"
                    "<h3 style='margin:0 0 12px 0;font-size:1.05rem;color:var(--rc-text);'>Offer &amp; Content Summary</h3>"
                    "<div class='panel-grid'>"
                    "<div class='mini-panel'>"
                    "<h4>Offer Details</h4>"
                    f"<p><strong>Offer Key</strong><br><code>{html.escape(str(st.session_state.get('offer_key', 'Not set')))}</code></p>"
                    f"<p style='margin-top:8px;'><strong>Task / Reward</strong><br>{html.escape(str(st.session_state.get('task_type', 'Not set')))} / {html.escape(str(st.session_state.get('reward_type', 'Not set')))}</p>"
                    "</div>"
                    "<div class='mini-panel'>"
                    "<h4>Template Payload</h4>"
                    f"<p><strong>Send Conditions</strong><br>{html.escape(send_conditions_label)}</p>"
                    f"<p style='margin-top:8px;'><strong>Variants</strong><br>{html.escape(variants_label)}</p>"
                    "</div>"
                    "<div class='mini-panel'>"
                    "<h4>Content Scope</h4>"
                    f"<p><strong>Languages</strong><br>{len(st.session_state.get('parsed_docs', []))}</p>"
                    f"<p style='margin-top:8px;'><strong>Markets</strong><br>{html.escape(', '.join(st.session_state.get('audit_markets', [])) or 'Auto-detect pending')}</p>"
                    "</div>"
                    "</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            
            st.markdown(
                (
                    "<div class='console-panel'>"
                    "<span class='section-kicker'>PACKAGES</span>"
                    "<h3 style='margin:0 0 12px 0;font-size:1.05rem;color:var(--rc-text);'>CMS Export Packages</h3>"
                    "<div class='panel-grid'>"
                    "<div class='mini-panel'><h4>SMS Package</h4><ul><li>CampaignWizardSmsTemplate</li><li>Template body content</li><li>Per-language XML files</li></ul></div>"
                    "<div class='mini-panel'><h4>OMS Package</h4><ul><li>CampaignWizardOmsTemplate</li><li>Title, body, CTA</li><li>ClaimedReward included by default</li></ul></div>"
                    "<div class='mini-panel'><h4>T&C Package</h4><ul><li>CampaignWizardTCTemplate</li><li>Significant terms</li><li>Full terms & conditions</li></ul></div>"
                    "</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            
            st.divider()
            
            # Audit Report Metadata — styled to match the rest of the export tab
            audit_offer_type = st.session_state.get("offer_key", "Not set")
            st.session_state["audit_offer_type"] = audit_offer_type
            detected_markets = detect_markets_from_languages(parsed_docs)
            st.session_state["audit_markets"] = detected_markets

            st.markdown(
                (
                    "<div class='console-panel'>"
                    "<span class='section-kicker'>AUDIT CONTEXT</span>"
                    "<h3 style='margin:0 0 4px 0;font-size:1.1rem;color:var(--rc-text);'>Report Metadata</h3>"
                    "<p style='margin:0 0 12px 0;color:var(--rc-muted);font-size:0.82rem;'>Offer type and markets are auto-detected. Notes are included in the downloaded report.</p>"
                    "<div class='panel-grid' style='grid-template-columns:1fr 1fr;'>"
                    f"<div class='mini-panel'><p><strong>Offer Type</strong><br><code>{html.escape(str(audit_offer_type))}</code></p></div>"
                    f"<div class='mini-panel'><p><strong>Markets</strong><br>{html.escape(', '.join(detected_markets)) if detected_markets else '<em>None detected</em>'}</p></div>"
                    "</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

            audit_notes = st.text_area(
                "Report Notes",
                value=st.session_state.get("audit_notes", ""),
                height=100,
                placeholder="Optional: Context for this export, approvals, caveats, or rollout notes.",
                key="audit_notes_context",
                label_visibility="collapsed",
            )
            st.session_state["audit_notes"] = audit_notes
            
            st.divider()
            
            # Validation
            can_generate = True
            warnings = []
            
            if not st.session_state.get("offer_key"):
                warnings.append("Offer Key not configured")
                can_generate = False
            if not st.session_state.get("send_conditions"):
                warnings.append("No Send Conditions selected")
                can_generate = False
            if not st.session_state.get("variants"):
                warnings.append("No Template Variants detected in documents")
                can_generate = False
            
            if warnings:
                for w in warnings:
                    st.warning(f"⚠️ {w}")

            # Optional QA gate (soft block with explicit override)
            readiness = build_language_readiness(effective_docs)
            if readiness["has_issues"]:
                invalid_details = []
                for lang, info in readiness["by_language"].items():
                    if info.get("status") == "invalid" and info.get("invalid_tokens"):
                        token_list = ", ".join([f"%%{t}%%" for t in info["invalid_tokens"][:4]])
                        if len(info["invalid_tokens"]) > 4:
                            token_list += f" (+{len(info['invalid_tokens']) - 4} more)"
                        invalid_details.append(f"{lang}: {token_list}")
                st.warning(
                    f"QA issues detected: {readiness['missing_count']} language(s) with missing content, "
                    f"{readiness['invalid_count']} language(s) with invalid placeholders."
                )
                if invalid_details:
                    st.caption("Remaining invalid placeholders: " + " | ".join(invalid_details))
                allow_with_issues = st.checkbox(
                    "Allow generation with QA issues",
                    value=False,
                    help="Enable only if you intentionally want to generate packages despite QA issues.",
                )
                if not allow_with_issues:
                    can_generate = False
            else:
                st.success("✅ QA check passed: all languages are ready.")
            
            st.divider()
            
            if st.button("🚀 Generate CMS Packages", type="primary", width="stretch", disabled=not can_generate):
                with st.spinner("Generating CMS packages..."):
                    try:
                        # Use effective docs so generation/report include widget edits and fix buffers
                        parsed_docs = build_effective_parsed_docs(st.session_state["parsed_docs"])
                        
                        # Create temp output directory
                        output_dir = Path(tempfile.mkdtemp())
                        
                        # Generate packages
                        generated_paths = generate_cms_packages(
                            parsed_docs=parsed_docs,
                            offer_key=st.session_state["offer_key"],
                            task_type=st.session_state["task_type"],
                            reward_type=st.session_state["reward_type"],
                            send_conditions=st.session_state["send_conditions"],
                            variants=st.session_state["variants"],
                            bonus_product=st.session_state.get("bonus_product"),
                            output_dir=output_dir,
                            image_key=st.session_state.get("image_key"),
                            image_id=st.session_state.get("image_id"),
                        )
                        
                        st.success("✅ CMS packages generated successfully!")
                        
                        # Generate Audit Report
                        st.subheader("📋 Audit Report")

                        # Build structured QA issues and content edit logs for audit report
                        readiness_snapshot = build_language_readiness(parsed_docs)
                        qa_issues_for_report: dict[str, list] = {}
                        for lang, info in readiness_snapshot["by_language"].items():
                            issues = []
                            for _ in info.get("missing_issues", []):
                                issues.append({"type": "missing"})
                            for _ in range(info.get("invalid_count", 0)):
                                issues.append({"type": "invalid"})
                            qa_issues_for_report[lang] = issues

                        original_docs = st.session_state.get("original_parsed_docs", [])
                        raw_content_edits = collect_content_edit_log(original_docs, parsed_docs)
                        filtered_content_edits = filter_auto_fix_only_edits(
                            raw_content_edits,
                            st.session_state.get("qa_fix_details", {}),
                        )
                        
                        fixes_applied_report = st.session_state.get("qa_fixes_applied", {})
                        fix_details_report = st.session_state.get("qa_fix_details", {})
                        if not fixes_applied_report and st.session_state.get("qa_fix_events"):
                            fixes_applied_report = {}
                            fix_details_report = {}
                            for event in st.session_state.get("qa_fix_events", []):
                                lang = event.get("language", "")
                                field = event.get("field", "")
                                if not lang or not field:
                                    continue
                                count = int(event.get("count", 0) or 0)
                                fixes_applied_report.setdefault(lang, {})
                                fixes_applied_report[lang][field] = fixes_applied_report[lang].get(field, 0) + count
                                fix_details_report.setdefault(lang, {})
                                details = fix_details_report[lang].setdefault(field, [])
                                for pair in event.get("replacements", []):
                                    if pair not in details:
                                        details.append(pair)

                        audit_report = build_report_from_session(
                            document_name=st.session_state.get("document_name", "Unknown"),
                            upload_timestamp=st.session_state.get("upload_timestamp", datetime.now()),
                            parsed_docs=parsed_docs,
                            generated_paths=generated_paths,
                            qa_issues=qa_issues_for_report,
                            fixes_applied=fixes_applied_report,
                            fix_details=fix_details_report,
                            language_names=LANGUAGE_NAMES,
                            offer_type=st.session_state.get("audit_offer_type", st.session_state.get("offer_key", "Unknown")),
                            template_version="",
                            markets=st.session_state.get("audit_markets", []),
                            user_notes=st.session_state.get("audit_notes", ""),
                            content_edits=filtered_content_edits,
                            task_type=st.session_state.get("task_type", ""),
                            reward_type=st.session_state.get("reward_type", ""),
                            send_conditions=st.session_state.get("send_conditions", []),
                            variants=st.session_state.get("variants", []),
                        )
                        
                        report_markdown = audit_report.generate_markdown_report()
                        
                        # Display report summary
                        with st.expander("📄 View Full Audit Report", expanded=False):
                            st.markdown(report_markdown, unsafe_allow_html=True)
                        
                        # Download button for report
                        report_filename = f"AuditReport_{st.session_state.get('offer_key', 'Unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        dl_col1, dl_col2 = st.columns(2)
                        with dl_col1:
                            report_html = audit_report.generate_html_report()
                            st.download_button(
                                label="📥 Download Audit Report (Confluence)",
                                data=report_html.encode(),
                                file_name=f"{report_filename}.html",
                                mime="text/html",
                                width="stretch",
                                help="HTML format — open in browser, Ctrl+A, Ctrl+C, paste into Confluence",
                            )
                        with dl_col2:
                            st.download_button(
                                label="📥 Download Audit Report (Markdown)",
                                data=report_markdown.encode(),
                                file_name=f"{report_filename}.md",
                                mime="text/markdown",
                                width="stretch",
                                help="Raw Markdown for Git, docs, or local reference",
                            )
                        
                        st.divider()
                        
                        # Create download buttons for each package
                        st.subheader("📥 Download Packages")
                        
                        timestamp = datetime.now().strftime("%Y-%m-%d")
                        
                        for template_type, path in generated_paths.items():
                            # Create ZIP in memory
                            zip_buffer = BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                                for file_path in path.rglob("*"):
                                    if file_path.is_file():
                                        arcname = file_path.relative_to(path)
                                        zip_file.write(file_path, arcname)
                            
                            zip_buffer.seek(0)
                            
                            content_type_name = f"CampaignWizard{template_type}Template"
                            filename = f"MultiMCmsExport_{content_type_name}_{timestamp}_common_common_all.zip"
                            
                            st.download_button(
                                label=f"Download {template_type} Package",
                                data=zip_buffer.getvalue(),
                                file_name=filename,
                                mime="application/zip",
                                width="stretch",
                                help=f"Contains {template_type} templates for all languages",
                            )
                        
                        # Summary
                        st.divider()
                        st.success("✅ All packages ready for CMS upload!")
                        st.markdown("""
                        **Next steps:**
                        1. Download all 3 packages above
                        2. Import each into CMS admin:
                           - **SMS** → CampaignWizardSmsTemplate
                           - **OMS** → CampaignWizardOmsTemplate  
                           - **TC** → CampaignWizardTCTemplate
                        """)
                        
                        # Cleanup
                        shutil.rmtree(output_dir, ignore_errors=True)
                        
                    except Exception as e:
                        st.error(f"Error generating packages: {str(e)}")
                        raise e

    with tab4:
        st.header("🔍 Compare with Existing CMS Export")
        st.markdown("""
        Upload an existing CMS export to compare with your generated output.
        This helps identify what changed when updating existing templates.
        """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📂 Existing CMS Export")
            existing_zip = st.file_uploader(
                "Upload existing CMS export ZIP",
                type=["zip"],
                key="existing_cms_zip",
                help="The current version from CMS that you want to compare against"
            )
        
        with col2:
            st.subheader("📦 New CMS Export")
            new_zip = st.file_uploader(
                "Upload new/generated CMS export ZIP",
                type=["zip"],
                key="new_cms_zip",
                help="The newly generated package to compare"
            )
        
        if existing_zip and new_zip:
            st.divider()
            
            # Extract XML from both
            with st.spinner("Extracting and comparing..."):
                existing_files = extract_xml_from_cms_export(existing_zip)
                new_files = extract_xml_from_cms_export(new_zip)
                
                # Get all unique filenames
                all_files = set(existing_files.keys()) | set(new_files.keys())
                
                if not all_files:
                    st.warning("No XML files found in the uploads")
                else:
                    # File selector
                    sorted_files = sorted(all_files)
                    selected_file = st.selectbox(
                        "Select file to compare",
                        sorted_files,
                        help="Choose an XML file to see the diff"
                    )
                    
                    # Status indicators
                    status_col1, status_col2, status_col3 = st.columns(3)
                    with status_col1:
                        only_in_existing = set(existing_files.keys()) - set(new_files.keys())
                        if only_in_existing:
                            st.warning(f"⚠️ {len(only_in_existing)} file(s) only in existing")
                    with status_col2:
                        only_in_new = set(new_files.keys()) - set(existing_files.keys())
                        if only_in_new:
                            st.info(f"➕ {len(only_in_new)} new file(s)")
                    with status_col3:
                        common = set(existing_files.keys()) & set(new_files.keys())
                        st.success(f"📄 {len(common)} file(s) to compare")
                    
                    st.divider()
                    
                    # Show diff for selected file
                    if selected_file:
                        existing_content = existing_files.get(selected_file, "")
                        new_content = new_files.get(selected_file, "")
                        
                        if not existing_content and new_content:
                            st.info(f"🆕 **New file** - `{selected_file}` doesn't exist in the old export")
                            st.code(new_content, language="xml")
                        elif existing_content and not new_content:
                            st.warning(f"🗑️ **Removed** - `{selected_file}` doesn't exist in the new export")
                            st.code(existing_content, language="xml")
                        elif existing_content == new_content:
                            st.success(f"✅ **No changes** - `{selected_file}` is identical")
                            with st.expander("View content"):
                                st.code(existing_content, language="xml")
                        else:
                            st.info(f"📝 **Modified** - `{selected_file}` has changes")
                            
                            # Format for better comparison
                            existing_formatted = format_xml_for_diff(existing_content)
                            new_formatted = format_xml_for_diff(new_content)
                            
                            # Generate and display diff
                            diff_html = generate_diff_html(
                                existing_formatted, 
                                new_formatted,
                                "Existing (CMS)",
                                "Generated (New)"
                            )
                            st.markdown(diff_html, unsafe_allow_html=True)
                            
                            # Also show raw side-by-side
                            with st.expander("View raw XML side-by-side"):
                                raw_col1, raw_col2 = st.columns(2)
                                with raw_col1:
                                    st.markdown("**Existing:**")
                                    st.code(existing_content, language="xml")
                                with raw_col2:
                                    st.markdown("**Generated:**")
                                    st.code(new_content, language="xml")
        
        elif existing_zip or new_zip:
            st.info("Upload both ZIPs to see the comparison")
        else:
            st.info("Upload two CMS export ZIPs to compare them")

    with tab5:
        st.header("📖 CMS Template Generator - Help")
        
        st.markdown("""
        ## Overview
        
        This tool converts localized Word documents into CMS-ready template packages for Campaign Wizard.
        It generates three package types:
        
        | Package | CMS Content Type | Purpose |
        |---------|-----------------|---------|
        | **SMS** | CampaignWizardSmsTemplate | Text messages |
        | **OMS** | CampaignWizardOmsTemplate | On-site messages (notifications) |
        | **TC** | CampaignWizardTCTemplate | Terms & Conditions |
        
        ---
        
        ## Word Document Structure
        
        ### Folder & Naming
        - Create a folder with Word documents named: `{LANGUAGE}_{OfferName}.docx`
        - Examples: `EN_WelcomeBonus.docx`, `DE_WelcomeBonus.docx`, `FI_WelcomeBonus.docx`
        - ZIP the folder for upload
        
        ### Document Sections (Headers)
        
        Each Word document should have these **exact** headers:
        
        ```
        LAUNCH - SMS
        (SMS body text for launch)
        
        REMINDER - SMS  
        (SMS body text for reminder)
        
        LAUNCH - OMS - variant A
        (Title on one line)
        (Body content - can use BBCode)
        (CTA text on last line)
        
        REMINDER - OMS - variant A
        (Same structure as launch)
        
        REWARD RECEIVED – OMS – Template A
        (Title)
        (Body)
        (CTA)
        
        Significant Terms
        (Short terms summary)
        
        Terms and Conditions
        (Full T&C text)
        ```
        
        ### Variants
        
        OMS templates support variants (A, B, etc.) for A/B testing:
        - `LAUNCH - OMS - variant A`
        - `LAUNCH - OMS - variant B`
        - `REWARD RECEIVED – OMS – Template A` (send condition: `ClaimedReward-TemplateA`)
        
        SMS templates can also have variants:
        - `LAUNCH - SMS - variant A`
        
        ---
        
        ## Placeholders
        
        Use `%%PlaceholderName%%` format in your content. Valid placeholders:
        
        ### Common
        - `%%BrandName%%` - Brand display name
        - `%%BrandDomain%%` - Brand website domain
        - `%%PalantirDomain%%` - Tracking domain (used for SMS links)
        - `%%OfferId%%` - Campaign offer ID
        - `%%CampaignEndDateAndTime%%` - When offer expires
        
        ### Customer
        - `%%CustomerFirstName%%` - Player's first name
        - `%%CustomerLastName%%` - Player's last name
        
        ### Task-specific
        - `%%DepositFulfillmentAmount%%` - Required deposit amount
        - `%%WagerTaskAmount%%` - Required wager amount
        - `%%WagerTaskOn%%` - Where to wager (games/categories)
        
        ### Reward-specific
        - `%%NrOfFreespins%%` - Number of free spins
        - `%%FreespinGames%%` - Games for free spins
        - `%%BonusAmount%%` - Bonus money amount
        - `%%CashRewardAmount%%` - Cash reward amount
        
        ⚠️ Invalid placeholders are highlighted in the Preview tab.
        
        ---
        
        ## OMS Images
        
        Select an image in the sidebar. Available images are pre-loaded from CMS.
        The image is linked via `LinkedContentKey` and `LinkedDocumentKey`.
        
        ---
        
        ## BBCode in OMS
        
        OMS body supports BBCode formatting:
        
        | BBCode | Result |
        |--------|--------|
        | `[b]bold[/b]` | **bold** |
        | `[i]italic[/i]` | *italic* |
        | `[u]underline[/u]` | <u>underline</u> |
        | `[ul][li]item[/li][/ul]` | Bullet list |
        | `[url=http://...]text[/url]` | Link |
        
        ---
        
        ## Workflow
        
        1. **Configure** - Set task type, reward type, image in sidebar
        2. **Upload** - Upload ZIP with Word documents
        3. **Preview** - Review & edit extracted content
        4. **Generate** - Download CMS packages
        5. **Import** - Upload each package to CMS admin
        
        ---
        
        ## CMS Import
        
        1. Go to CMS Admin → Content Export / Import
        2. Select the correct content type
        3. Upload the ZIP (keep filename as-is)
        4. Verify import success
        
        ---
        
        ## Troubleshooting
        
        | Issue | Solution |
        |-------|----------|
        | No templates found | Check Word document headers match exactly |
        | Import fails | Ensure UTF-8 encoding, check for special characters |
        | Image not showing | Verify image ID exists in target environment |
        | Placeholders broken | Check `%%Name%%` format (double percent signs) |
        
        ---
        
        ## Compare Tab
        
        Use the Compare tab to:
        - Upload an existing CMS export and your generated package
        - See side-by-side diff of changes
        - Identify what was added, removed, or modified
        
        This is useful when updating existing templates.
        """)


if __name__ == "__main__":
    main()
