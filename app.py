"""
CMS Template Generator Dashboard

Streamlit app for converting localized Word documents into CMS-ready template packages.
"""

import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from io import BytesIO

import streamlit as st
import pandas as pd

from config import (
    LANGUAGE_MAPPING,
    LANGUAGE_NAMES,
    TASK_TYPES,
    REWARD_TYPES,
    BONUS_PRODUCTS,
    SEND_CONDITIONS,
    OMS_IMAGES,
)
from word_parser import parse_documents_from_folder, ParsedDocument
from xml_generator import generate_cms_packages
import re
import difflib
import xml.etree.ElementTree as ET


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


def bbcode_to_html(text: str) -> str:
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
    
    # Highlight placeholders with a subtle colored badge
    html = re.sub(
        r'%%([A-Za-z0-9_]+)%%',
        r'<code style="background: linear-gradient(135deg, #2d5a27 0%, #1a3d1a 100%); color: #90EE90; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; white-space: nowrap;">%%\1%%</code>',
        html
    )
    
    # Convert newlines to <br>
    html = html.replace('\n', '<br>')
    
    return html


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
st.set_page_config(
    page_title="CMS Template Generator",
    page_icon="📝",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .stAlert > div {
        padding: 0.5rem 1rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 4px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        border-radius: 4px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


def main():
    st.title("📝 CMS Template Generator")
    st.markdown("Convert localized Word documents into CMS-ready template packages (SMS, OMS, TC)")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Offer Configuration")
        
        # Check for auto-detected values (set during upload processing)
        detected_task = st.session_state.get("detected_task_type")
        detected_reward = st.session_state.get("detected_reward_type")
        detected_image = st.session_state.get("detected_image")
        
        # Check if we just detected new values and need to apply them
        apply_detection = st.session_state.pop("apply_detection", False)
        
        # Task Type - with custom option
        task_type_options = TASK_TYPES + ["➕ Custom..."]
        
        # Initialize or update widget key based on detection
        if apply_detection and detected_task and detected_task in task_type_options:
            st.session_state["task_type_select"] = detected_task
        elif "task_type_select" not in st.session_state:
            # First render - set default
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
        
        # Initialize or update widget key based on detection
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
        
        # Bonus Product (optional) - with custom option
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
        
        # OMS Image (optional)
        st.subheader("🖼️ OMS Image")
        image_options = list(OMS_IMAGES.keys())
        
        # Initialize or update widget key based on detection
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
        )
        
        if detected_image and selected_image_display == detected_image:
            st.caption("🔍 Auto-selected based on reward type")
        
        image_tuple = OMS_IMAGES.get(selected_image_display, ("CW_BonusFreeSpin_casino", "3736707", "6f9506db0ced4118993357b114c831ce.jpg"))
        selected_image_key = image_tuple[0]
        selected_image_id = image_tuple[1]
        selected_image_file = image_tuple[2] if len(image_tuple) > 2 else None
        
        # Show image preview
        if selected_image_file:
            image_path = Path(__file__).parent / "images" / selected_image_file
            if image_path.exists():
                st.image(str(image_path), caption=selected_image_display, width=150)
        st.caption(f"CMS Key: `{selected_image_key}` | ID: `{selected_image_id}`")
        
        st.divider()
        
        # Send Conditions
        st.subheader("Send Conditions")
        selected_conditions = []
        for condition in SEND_CONDITIONS:
            if st.checkbox(condition, value=condition in ["NotOptedIn", "JoinedCampaign", "CampaignHasStarted"]):
                selected_conditions.append(condition)
        
        # Custom send condition
        custom_condition = st.text_input(
            "Custom Send Condition (optional)",
            placeholder="e.g., TaskCompleted",
            help="Add a new send condition if needed",
        )
        if custom_condition:
            selected_conditions.append(custom_condition)
            st.caption(f"✅ Added: `{custom_condition}`")
        
        st.divider()
        
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
            st.success(f"**Offer Key:** `{offer_key}`")
        else:
            offer_key = ""
            st.info("Configure Task Type and Reward Type to see offer key")
    
    # Main content area
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📤 Upload Content", "👁️ Preview", "📥 Generate & Download", "🔍 Compare", "📖 Help"])
    
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
                # Extract ZIP to temp directory
                temp_dir = Path(tempfile.mkdtemp())
                
                try:
                    with zipfile.ZipFile(uploaded_file, "r") as zip_ref:
                        zip_ref.extractall(temp_dir)
                    
                    # Find the folder with Word docs (might be nested)
                    docx_files = list(temp_dir.rglob("*.docx"))
                    if not docx_files:
                        st.error("No Word documents found in ZIP")
                    else:
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
                        
                        # Store in session state
                        st.session_state["parsed_docs"] = parsed_docs
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
                            use_container_width=True,
                            height=table_height,
                            hide_index=True
                        )
                    
                finally:
                    # Cleanup temp dir
                    shutil.rmtree(temp_dir, ignore_errors=True)
    
    with tab2:
        st.header("Step 2: Preview Extracted Content")
        
        if "parsed_docs" not in st.session_state:
            st.info("Upload a ZIP file first to see preview")
        else:
            parsed_docs = st.session_state["parsed_docs"]
            
            # Language selector with full names
            languages = [doc.language_code for doc in parsed_docs]
            
            def format_language(code: str) -> str:
                """Format language code with full name."""
                name = LANGUAGE_NAMES.get(code, code)
                return f"{code} - {name}"
            
            selected_lang = st.selectbox(
                "Select Language to Preview", 
                languages,
                format_func=format_language
            )
            
            selected_doc = next((d for d in parsed_docs if d.language_code == selected_lang), None)
            
            if selected_doc:
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
                            char_count, color, char_msg = get_sms_char_info(sms_body)
                            invalid_placeholders = validate_placeholders(sms_body)
                            missing = check_missing_content("SMS", body=sms_body)
                            
                            status_icon = "✅" if not invalid_placeholders and not missing and color == "green" else "⚠️"
                            expander_label = f"{status_icon} {sms_type} - Template {template.variant} ({template.send_condition})"
                            
                            with st.expander(expander_label):
                                sms_key = f"sms_{selected_lang}_{idx}_{sms_type}_{template.variant}"
                                edited_body = st.text_area("Body", value=sms_body, height=100, key=sms_key)
                                
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
                                    st.error(f"❌ Invalid placeholders: {', '.join(['%%' + p + '%%' for p in invalid])}")
                                
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
                            
                            all_text = oms_title + " " + oms_body + " " + oms_cta
                            invalid_placeholders = validate_placeholders(all_text)
                            missing = check_missing_content("OMS", title=oms_title, body=oms_body, cta=oms_cta)
                            
                            status_icon = "✅" if not invalid_placeholders and not missing else "⚠️"
                            expander_label = f"{status_icon} {oms_type} - Template {template.variant} ({template.send_condition})"
                            
                            with st.expander(expander_label):
                                title_key = f"oms_title_{selected_lang}_{idx}_{oms_type}_{template.variant}"
                                body_key = f"oms_body_{selected_lang}_{idx}_{oms_type}_{template.variant}"
                                cta_key = f"oms_cta_{selected_lang}_{idx}_{oms_type}_{template.variant}"
                                
                                edited_title = st.text_input("Title", value=oms_title, key=title_key)
                                edited_body = st.text_area("Body (BBCode)", value=oms_body, height=150, key=body_key)
                                edited_cta = st.text_input("CTA", value=oms_cta, key=cta_key)
                                
                                if edited_body:
                                    st.markdown("**Preview:**")
                                    preview_html = bbcode_to_html(edited_body)
                                    # Use theme-aware styling for dark mode support
                                    st.markdown(
                                        f'<div style="background-color: rgba(255, 255, 255, 0.1); '
                                        f'padding: 12px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.2); '
                                        f'font-size: 14px; line-height: 1.6;">{preview_html}</div>',
                                        unsafe_allow_html=True
                                    )
                                
                                all_edited = edited_title + " " + edited_body + " " + edited_cta
                                invalid = validate_placeholders(all_edited)
                                if invalid:
                                    st.error(f"❌ Invalid placeholders: {', '.join(['%%' + p + '%%' for p in invalid])}")
                                
                                for warn in check_missing_content("OMS", title=edited_title, body=edited_body, cta=edited_cta):
                                    st.warning(warn)
                    else:
                        st.warning("No OMS templates found")
                
                # Terms & Conditions - full width below columns
                st.subheader("📋 Terms & Conditions")
                if selected_doc.tc:
                    tc_sig = selected_doc.tc.significant_terms or ""
                    tc_full = selected_doc.tc.terms_and_conditions or ""
                    
                    all_tc_text = tc_sig + " " + tc_full
                    invalid_tc = validate_placeholders(all_tc_text)
                    tc_missing = []
                    if not tc_sig.strip():
                        tc_missing.append("Significant Terms empty")
                    if not tc_full.strip():
                        tc_missing.append("Full T&Cs empty")
                    
                    if invalid_tc or tc_missing:
                        st.warning(f"⚠️ Issues found: {', '.join(tc_missing) if tc_missing else ''} {', '.join(['Invalid: %%' + p + '%%' for p in invalid_tc]) if invalid_tc else ''}")
                    
                    tc_col1, tc_col2 = st.columns(2)
                    with tc_col1:
                        edited_sig = st.text_area("Significant Terms", value=tc_sig, height=200, key=f"tc_sig_{selected_lang}")
                        sig_invalid = validate_placeholders(edited_sig)
                        if sig_invalid:
                            st.error(f"❌ Invalid: {', '.join(['%%' + p + '%%' for p in sig_invalid])}")
                        if not edited_sig.strip():
                            st.warning("⚠️ Significant Terms is empty")
                            
                    with tc_col2:
                        edited_full = st.text_area("Full Terms & Conditions", value=tc_full, height=200, key=f"tc_full_{selected_lang}")
                        full_invalid = validate_placeholders(edited_full)
                        if full_invalid:
                            st.error(f"❌ Invalid: {', '.join(['%%' + p + '%%' for p in full_invalid])}")
                        if not edited_full.strip():
                            st.warning("⚠️ Full T&Cs is empty")
                else:
                    st.warning("No T&Cs found")
    
    with tab3:
        st.header("Step 3: Generate CMS Packages")
        
        if "parsed_docs" not in st.session_state:
            st.info("Upload and parse documents first")
        else:
            parsed_docs = st.session_state.get("parsed_docs", [])
            
            # Show configuration summary
            st.subheader("📋 Configuration Summary")
            
            config_col1, config_col2, config_col3 = st.columns(3)
            
            with config_col1:
                st.markdown("**Offer Details**")
                st.write("Offer Key:", st.session_state.get("offer_key", "Not set"))
                st.write("Task Type:", st.session_state.get("task_type", "Not set"))
                st.write("Reward Type:", st.session_state.get("reward_type", "Not set"))
            
            with config_col2:
                st.markdown("**Templates**")
                st.write("Send Conditions:", ", ".join(st.session_state.get("send_conditions", [])))
                st.write("Detected Variants:", ", ".join(st.session_state.get("variants", [])))
            
            with config_col3:
                st.markdown("**Content**")
                st.write("Languages:", len(st.session_state.get("parsed_docs", [])))
            
            st.divider()
            
            # Package preview
            st.subheader("📦 Packages to Generate")
            pkg_col1, pkg_col2, pkg_col3 = st.columns(3)
            
            with pkg_col1:
                st.markdown("**1. SMS Package**")
                st.caption("CampaignWizardSmsTemplate")
                st.write("• Template body text")
                st.write("• Per-language XML files")
            
            with pkg_col2:
                st.markdown("**2. OMS Package**")
                st.caption("CampaignWizardOmsTemplate")
                st.write("• Title, body, CTA")
                st.write("• Per-language XML files")
            
            with pkg_col3:
                st.markdown("**3. TC Package**")
                st.caption("CampaignWizardTCTemplate")
                st.write("• Significant terms")
                st.write("• Full T&Cs")
            
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
            
            st.divider()
            
            if st.button("🚀 Generate CMS Packages", type="primary", use_container_width=True, disabled=not can_generate):
                with st.spinner("Generating CMS packages..."):
                    try:
                        # Sync edited values from preview back to parsed_docs
                        parsed_docs = st.session_state["parsed_docs"]
                        for doc in parsed_docs:
                            lang = doc.language_code
                            
                            # Sync SMS edits
                            idx = 0
                            if doc.launch_sms:
                                for template in doc.launch_sms.templates:
                                    key = f"sms_{lang}_{idx}_Launch_{template.variant}"
                                    if key in st.session_state:
                                        template.body = st.session_state[key]
                                    idx += 1
                            if doc.reminder_sms:
                                for template in doc.reminder_sms.templates:
                                    key = f"sms_{lang}_{idx}_Reminder_{template.variant}"
                                    if key in st.session_state:
                                        template.body = st.session_state[key]
                                    idx += 1
                            
                            # Sync OMS edits
                            idx = 0
                            if doc.launch_oms:
                                for template in doc.launch_oms.templates:
                                    title_key = f"oms_title_{lang}_{idx}_Launch_{template.variant}"
                                    body_key = f"oms_body_{lang}_{idx}_Launch_{template.variant}"
                                    cta_key = f"oms_cta_{lang}_{idx}_Launch_{template.variant}"
                                    if title_key in st.session_state:
                                        template.title = st.session_state[title_key]
                                    if body_key in st.session_state:
                                        template.body = st.session_state[body_key]
                                    if cta_key in st.session_state:
                                        template.cta = st.session_state[cta_key]
                                    idx += 1
                            if doc.reminder_oms:
                                for template in doc.reminder_oms.templates:
                                    title_key = f"oms_title_{lang}_{idx}_Reminder_{template.variant}"
                                    body_key = f"oms_body_{lang}_{idx}_Reminder_{template.variant}"
                                    cta_key = f"oms_cta_{lang}_{idx}_Reminder_{template.variant}"
                                    if title_key in st.session_state:
                                        template.title = st.session_state[title_key]
                                    if body_key in st.session_state:
                                        template.body = st.session_state[body_key]
                                    if cta_key in st.session_state:
                                        template.cta = st.session_state[cta_key]
                                    idx += 1
                            
                            # Sync Reward OMS edits
                            if doc.reward_oms:
                                for idx, template in enumerate(doc.reward_oms.templates):
                                    title_key = f"reward_oms_title_{lang}_{idx}_{template.variant}"
                                    body_key = f"reward_oms_body_{lang}_{idx}_{template.variant}"
                                    cta_key = f"reward_oms_cta_{lang}_{idx}_{template.variant}"
                                    if title_key in st.session_state:
                                        template.title = st.session_state[title_key]
                                    if body_key in st.session_state:
                                        template.body = st.session_state[body_key]
                                    if cta_key in st.session_state:
                                        template.cta = st.session_state[cta_key]
                            
                            # Sync T&C edits
                            if doc.tc:
                                sig_key = f"tc_sig_{lang}"
                                full_key = f"tc_full_{lang}"
                                if sig_key in st.session_state:
                                    doc.tc.significant_terms = st.session_state[sig_key]
                                if full_key in st.session_state:
                                    doc.tc.terms_and_conditions = st.session_state[full_key]
                        
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
                                use_container_width=True,
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
