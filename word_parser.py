"""
Word Document Parser for CMS Template Generator

Extracts structured content from localization Word documents.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from docx import Document
from config import SECTION_MARKERS, TEMPLATE_VARIANTS, LANGUAGE_MAPPING


@dataclass
class TemplateContent:
    """Content for a single template variant."""
    variant: str
    title: Optional[str] = None
    body: Optional[str] = None
    cta: Optional[str] = None
    cta_mobile: Optional[str] = None
    send_condition: str = "NotOptedIn"  # NotOptedIn (Launch) or JoinedCampaign (Reminder)


@dataclass
class OmsSection:
    """OMS section (Launch or Reminder) with multiple template variants."""
    section_type: str  # "Launch" or "Reminder"
    templates: list[TemplateContent] = field(default_factory=list)


@dataclass
class SmsSection:
    """SMS section (Launch or Reminder) with multiple template variants."""
    section_type: str  # "Launch" or "Reminder"
    templates: list[TemplateContent] = field(default_factory=list)


@dataclass
class TcSection:
    """Terms & Conditions section."""
    significant_terms: Optional[str] = None
    terms_and_conditions: Optional[str] = None


@dataclass
class MyOffersSection:
    """My Offers inbox content."""
    headline: Optional[str] = None
    sub_headline: Optional[str] = None
    task: Optional[str] = None
    reward: Optional[str] = None


@dataclass
class ParsedDocument:
    """Complete parsed content from a Word document."""
    language_code: str
    offer_name: str
    my_offers: Optional[MyOffersSection] = None
    launch_oms: Optional[OmsSection] = None
    reminder_oms: Optional[OmsSection] = None
    reward_oms: Optional[OmsSection] = None
    launch_sms: Optional[SmsSection] = None
    reminder_sms: Optional[SmsSection] = None
    tc: Optional[TcSection] = None
    raw_paragraphs: list[str] = field(default_factory=list)


def extract_language_and_offer(filename: str) -> tuple[str, str]:
    """
    Extract language code and offer name from filename.
    Format: {LANGUAGE}_{offer_name}.docx
    
    Handles compound language codes like EN_PE, RU_ET by checking
    against known LANGUAGE_MAPPING keys.
    """
    stem = Path(filename).stem
    stem_upper = stem.upper()
    
    # Try to find longest matching language code from LANGUAGE_MAPPING
    # Sort by length descending to match longer codes first (e.g., EN_PE before EN)
    known_codes = sorted(LANGUAGE_MAPPING.keys(), key=len, reverse=True)
    
    for code in known_codes:
        if stem_upper.startswith(code + "_"):
            # Found a match - the rest is the offer name
            offer_name = stem[len(code) + 1:]  # +1 for underscore
            return code, offer_name
    
    # Fallback: split on first underscore
    parts = stem.split("_", 1)
    if len(parts) == 2:
        return parts[0].upper(), parts[1]
    return stem.upper(), stem


def parse_word_document(file_path: Path) -> ParsedDocument:
    """
    Parse a Word document and extract structured content.
    
    Args:
        file_path: Path to the .docx file
        
    Returns:
        ParsedDocument with all extracted sections
    """
    doc = Document(file_path)
    language_code, offer_name = extract_language_and_offer(file_path.name)
    
    # Extract all paragraphs with their text, preserving bullet list formatting.
    # Also include table-cell text because many templates are authored in tables.
    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            # Check if this is a list item (bullet or numbered)
            is_list_item = False
            if para._p.pPr is not None and para._p.pPr.numPr is not None:
                is_list_item = True
            else:
                try:
                    if para.style and 'list' in para.style.name.lower():
                        is_list_item = True
                except Exception:
                    pass  # Skip style check for corrupted docs
            
            # Prefix list items with bullet character
            if is_list_item:
                text = "• " + text
            
            paragraphs.append(text)

    # Capture text authored inside tables (cells are not included in doc.paragraphs).
    # Table-based docs use key-value rows: [Label, Value]. Merged cells produce
    # duplicate text across columns, so we deduplicate per-row.
    _CMS_METADATA_RE = re.compile(
        r"^CampaignWizard(Oms|Sms|TC)Template\.", re.IGNORECASE
    )
    for table in doc.tables:
        for row in table.rows:
            seen_in_row = set()
            for cell in row.cells:
                for para in cell.paragraphs:
                    text = para.text.strip()
                    # Normalize non-breaking spaces
                    text = text.replace("\xa0", " ")
                    if not text:
                        continue
                    # Skip CMS metadata rows (e.g. "CampaignWizardOmsTemplate.Deposit-...")
                    if _CMS_METADATA_RE.match(text):
                        continue
                    # Deduplicate merged cells within the same row
                    if text in seen_in_row:
                        continue
                    seen_in_row.add(text)

                    is_list_item = False
                    if para._p.pPr is not None and para._p.pPr.numPr is not None:
                        is_list_item = True
                    else:
                        try:
                            if para.style and "list" in para.style.name.lower():
                                is_list_item = True
                        except Exception:
                            pass  # Skip style check for corrupted docs

                    if is_list_item:
                        text = "• " + text

                    paragraphs.append(text)
    
    parsed = ParsedDocument(
        language_code=language_code,
        offer_name=offer_name,
        raw_paragraphs=paragraphs,
    )
    
    # Parse sections based on markers
    parsed.my_offers = _parse_my_offers_section(paragraphs)
    parsed.launch_oms = _parse_oms_section(paragraphs, "Launch")
    parsed.reminder_oms = _parse_oms_section(paragraphs, "Reminder")
    parsed.reward_oms = _parse_reward_oms_section(paragraphs)
    parsed.launch_sms = _parse_sms_section(paragraphs, "Launch")
    parsed.reminder_sms = _parse_sms_section(paragraphs, "Reminder")
    parsed.tc = _parse_tc_section(paragraphs)
    
    return parsed


def _find_section_start(paragraphs: list[str], markers: list[str]) -> int:
    """Find the index where a section starts based on markers."""
    for i, para in enumerate(paragraphs):
        para_upper = para.upper().strip()
        for marker in markers:
            if marker in para_upper:
                return i
    return -1


def _find_tc_section_start(paragraphs: list[str], markers: list[str]) -> int:
    """Find T&C section start using strict matching (exact line or line starts with marker).
    
    This is stricter than _find_section_start because TC markers like 'TINGIMUSED'
    might appear as substrings in body text (e.g., 'Kehtivad tingimused. 21+.').
    """
    for i, para in enumerate(paragraphs):
        para_upper = para.upper().strip()
        for marker in markers:
            # Exact match (standalone header)
            if para_upper == marker:
                return i
            # Line starts with marker followed by nothing, space, or punctuation
            if para_upper.startswith(marker):
                rest = para_upper[len(marker):]
                if not rest or rest[0] in ' \t:–-':
                    return i
    return -1


def _parse_my_offers_section(paragraphs: list[str]) -> Optional[MyOffersSection]:
    """Parse MY OFFERS section for inbox content."""
    start = _find_section_start(paragraphs, SECTION_MARKERS["MY_OFFERS"])
    if start == -1:
        return None
    
    section = MyOffersSection()
    current_field = None
    
    # Exact T&C section headers for boundary detection
    tc_exact_headers = [
        "T&C", "T&CS", "TAC", "TERMS AND CONDITIONS", "SIGNIFICANT TERMS",
        "ΟΡΟΙ ΚΑΙ ΠΡΟΫΠΟΘΕΣΕΙΣ", "ΣΗΜΑΝΤΙΚΟΙ ΟΡΟΙ", "ΠΛΗΡΕΙΣ ΟΡΟΙ",
        "TÉRMINOS Y CONDICIONES", "TERMOS E CONDIÇÕES",
        "TERMINI E CONDIZIONI", "CONDITIONS GÉNÉRALES", "AGB",
        "TINGIMUSED", "OLULISED TINGIMUSED", "TÄIELIKUD TINGIMUSED",  # Estonian
        "REEGLID JA TINGIMUSED", "REEGLID",  # Estonian (alt)
        "REGLUR OG SKILYRÐI", "SKILYRÐI",  # Icelandic
        "KÄYTTÖEHDOT", "EHDOT",  # Finnish
        "TERMS & CONDITIONS",  # English variant
        "ŞARTLAR VE KOŞULLAR", "ŞARTLAR & KOŞULLAR",  # Turkish
        "ÖNEMLI ŞARTLAR VE KOŞULLAR",  # Turkish (significant)
        "WARUNKI I ZASADY", "ISTOTNE WARUNKI I ZASADY",  # Polish
        "BETINGELSER OG VILKÅR", "VIKTIGE BETINGELSER OG VILKÅR",  # Norwegian
        "NOTEIKUMI", "BŪTISKIE NOTEIKUMI",  # Latvian
    ]
    
    for para in paragraphs[start:]:
        para_upper = para.upper().strip()
        
        # Check for next major section
        if "LAUNCH OMS" in para_upper or ("SMS" in para_upper and "OMS" not in para_upper):
            break
        if para_upper in tc_exact_headers:
            break
            
        if "HEADLINE" in para_upper and "SUB" not in para_upper:
            current_field = "headline"
        elif "SUB-HEADLINE" in para_upper or "SUBHEADLINE" in para_upper:
            current_field = "sub_headline"
        elif "TASK" in para_upper:
            current_field = "task"
        elif "REWARD" in para_upper:
            current_field = "reward"
        elif current_field and para.strip():
            # Append content to current field
            current_value = getattr(section, current_field) or ""
            setattr(section, current_field, (current_value + " " + para).strip())
    
    return section


def _parse_oms_section(paragraphs: list[str], section_type: str) -> Optional[OmsSection]:
    """Parse OMS section (Launch or Reminder) with template variants."""
    marker_key = f"{section_type.upper()}_OMS"
    markers = SECTION_MARKERS.get(marker_key, [section_type.upper()])
    
    start = _find_section_start(paragraphs, markers)
    if start == -1:
        return None
    
    # Map section type to SendCondition
    send_condition = "NotOptedIn" if section_type == "Launch" else "JoinedCampaign"
    
    section = OmsSection(section_type=section_type)
    current_template = None
    current_field = None
    
    # Find end of section
    end = len(paragraphs)
    for i, para in enumerate(paragraphs[start + 1:], start + 1):
        para_upper = para.upper().strip()
        # Check if we hit another major section
        if section_type == "Launch" and "REMINDER" in para_upper:
            end = i
            break
        elif "REWARD RECEIVED" in para_upper:
            # End of templates, reward received section starts
            end = i
            break
        elif "SMS" in para_upper and "OMS" not in para_upper:
            end = i
            break
        # Use exact T&C section headers only
        tc_exact_headers = [
            "T&C", "T&CS", "TAC", "TERMS AND CONDITIONS", "SIGNIFICANT TERMS",
            "ΟΡΟΙ ΚΑΙ ΠΡΟΫΠΟΘΕΣΕΙΣ", "ΣΗΜΑΝΤΙΚΟΙ ΟΡΟΙ", "ΠΛΗΡΕΙΣ ΟΡΟΙ",
            "TÉRMINOS Y CONDICIONES", "TERMOS E CONDIÇÕES",
            "TERMINI E CONDIZIONI", "CONDITIONS GÉNÉRALES", "AGB",
            "TINGIMUSED", "OLULISED TINGIMUSED", "TÄIELIKUD TINGIMUSED",  # Estonian
            "REEGLID JA TINGIMUSED", "REEGLID",  # Estonian (alt)
            "REGLUR OG SKILYRÐI", "SKILYRÐI",  # Icelandic
            "KÄYTTÖEHDOT", "EHDOT",  # Finnish
            "TERMS & CONDITIONS",  # English variant
            "ŞARTLAR VE KOŞULLAR", "ŞARTLAR & KOŞULLAR",  # Turkish
            "ÖNEMLI ŞARTLAR VE KOŞULLAR",  # Turkish (significant)
            "WARUNKI I ZASADY", "ISTOTNE WARUNKI I ZASADY",  # Polish
            "BETINGELSER OG VILKÅR", "VIKTIGE BETINGELSER OG VILKÅR",  # Norwegian
            "NOTEIKUMI", "BŪTISKIE NOTEIKUMI",  # Latvian
        ]
        if para_upper in tc_exact_headers:
            end = i
            break
    
    for para in paragraphs[start:end]:
        para_stripped = para.strip()
        para_upper = para_stripped.upper()
        
        # Check for combined section+variant header (table-based docs)
        # e.g. "LAUNCH OMS - TemplateA", "REMINDER OMS - TemplateB"
        combined_match = re.search(r"(?:TEMPLATE|MALL|PÕHI)\s*([A-F])", para_upper)
        if combined_match and ("LAUNCH" in para_upper or "REMINDER" in para_upper or "OMS" in para_upper):
            if current_template:
                section.templates.append(current_template)
            current_template = TemplateContent(
                variant=combined_match.group(1),
                send_condition=send_condition
            )
            current_field = "title"
            continue

        # Check for "Launch A" / "Reminder A" format (DK-style docs)
        # e.g. "Launch A", "Reminder B" — section type + variant letter, no "Template" keyword
        short_variant_match = re.match(
            r"^(?:LAUNCH|REMINDER|OMS\s+(?:LAUNCH|REMINDER))\s+([A-F])$", para_upper
        )
        if short_variant_match:
            if current_template:
                section.templates.append(current_template)
            current_template = TemplateContent(
                variant=short_variant_match.group(1),
                send_condition=send_condition
            )
            current_field = "title"
            continue

        # Check for template variant marker
        variant_match = re.match(r"(?:TEMPLATE|MALL|PÕHI)\s*([A-F])", para_upper)
        if variant_match:
            if current_template:
                section.templates.append(current_template)
            current_template = TemplateContent(
                variant=variant_match.group(1),
                send_condition=send_condition
            )
            # Default to title field - content before BODY/CTA is the title
            # This handles docs with no explicit "Title" label
            current_field = "title"
            continue
        
        if current_template:
            # Check for field labels (explicit markers)
            # Handle various formats: "TITLE" alone, "TITLE:", "Title\n...", etc.
            
            # Check if paragraph starts with a label followed by newline (embedded label)
            # e.g., "Title\n🎮 Bet on Sports..." or "Body\n🎯 Get..."
            if para_stripped.upper().startswith("TITLE\n") or para_stripped.upper().startswith("TITLE:\n") or para_stripped.upper().startswith("PEALKIRI\n") or para_stripped.upper().startswith("PEALKIRI:\n"):
                current_field = "title"
                # Extract content after the label
                newline_pos = para_stripped.find('\n')
                if newline_pos > 0:
                    rest = para_stripped[newline_pos + 1:].strip()
                    if rest:
                        current_template.title = (current_template.title or "") + "\n" + rest if current_template.title else rest
                        current_template.title = current_template.title.strip()
                continue
            elif para_stripped.upper().startswith("BODY\n") or para_stripped.upper().startswith("BODY:\n"):
                current_field = "body"
                newline_pos = para_stripped.find('\n')
                if newline_pos > 0:
                    rest = para_stripped[newline_pos + 1:].strip()
                    if rest:
                        current_template.body = (current_template.body or "") + "\n" + rest if current_template.body else rest
                        current_template.body = current_template.body.strip()
                continue
            elif para_stripped.upper().startswith("CTA\n") or para_stripped.upper().startswith("CTA:\n"):
                current_field = "cta"
                newline_pos = para_stripped.find('\n')
                if newline_pos > 0:
                    rest = para_stripped[newline_pos + 1:].strip()
                    if rest:
                        current_template.cta = (current_template.cta or "") + "\n" + rest if current_template.cta else rest
                        current_template.cta = current_template.cta.strip()
                continue
            
            # Handle standalone labels (no embedded content)
            if para_upper in ("TITLE", "TITLE:", "PEALKIRI", "PEALKIRI:"):
                current_field = "title"
                continue
            elif para_upper.startswith("TITLE:") or para_upper.startswith("TITLE ") or para_upper.startswith("PEALKIRI:") or para_upper.startswith("PEALKIRI "):
                # "Title: actual content" or "Pealkiri: actual content" - strip prefix and use the rest
                current_field = "title"
                rest = para_stripped.split(None, 1)[1].strip() if len(para_stripped.split(None, 1)) > 1 else ""
                if rest:
                    current_template.title = rest
                continue
            elif para_upper == "BODY" or para_upper == "BODY:":
                current_field = "body"
                continue
            elif para_upper.startswith("BODY:") or para_upper.startswith("BODY "):
                # "Body: actual content" - strip prefix and use the rest
                current_field = "body"
                rest = para_stripped[5:].strip()
                if rest:
                    current_template.body = rest
                continue
            elif para_upper in ["CTA", "CTA:", "CALL TO ACTION", "CALLTOACTION"]:
                current_field = "cta"
                continue
            elif para_upper.startswith("CTA:") or para_upper.startswith("CTA "):
                # "CTA: actual content" - strip prefix and use the rest
                current_field = "cta"
                rest = para_stripped[4:].strip()
                if rest:
                    current_template.cta = rest
                continue
            elif current_field and para_stripped:
                current_value = getattr(current_template, current_field) or ""
                new_value = (current_value + "\n" + para_stripped).strip()
                setattr(current_template, current_field, new_value)
    
    # Don't forget the last template
    if current_template:
        section.templates.append(current_template)
    
    return section if section.templates else None


def _parse_reward_oms_section(paragraphs: list[str]) -> Optional[OmsSection]:
    """Parse REWARD RECEIVED OMS section with template variants."""
    markers = SECTION_MARKERS.get("REWARD_OMS", ["REWARD RECEIVED"])
    
    start = _find_section_start(paragraphs, markers)
    if start == -1:
        return None
    
    section = OmsSection(section_type="Reward")
    current_template = None
    current_field = None
    
    # Check if header itself contains template variant (e.g., "REWARD RECEIVED – OMS – Template A")
    header_para = paragraphs[start].upper()
    header_variant = None
    variant_match = re.search(r'(?:TEMPLATE|MALL|PÕHI)\s*([A-F])', header_para)
    if variant_match:
        header_variant = variant_match.group(1)
    
    # Find end of section - ends at T&C or SMS or next major section
    # Use exact T&C section headers only (not partial matches)
    tc_exact_headers = [
        "T&C", "T&CS", "TAC", "TERMS AND CONDITIONS", "SIGNIFICANT TERMS",
        "ΟΡΟΙ ΚΑΙ ΠΡΟΫΠΟΘΕΣΕΙΣ", "ΣΗΜΑΝΤΙΚΟΙ ΟΡΟΙ", "ΠΛΗΡΕΙΣ ΟΡΟΙ",
        "TÉRMINOS Y CONDICIONES", "TERMOS E CONDIÇÕES",
        "TERMINI E CONDIZIONI", "CONDITIONS GÉNÉRALES", "AGB",
        "TINGIMUSED", "OLULISED TINGIMUSED", "TÄIELIKUD TINGIMUSED",  # Estonian
        "REEGLID JA TINGIMUSED", "REEGLID",  # Estonian (alt)
        "REGLUR OG SKILYRÐI", "SKILYRÐI",  # Icelandic
        "KÄYTTÖEHDOT", "EHDOT",  # Finnish
        "TERMS & CONDITIONS",  # English variant
        "ŞARTLAR VE KOŞULLAR", "ŞARTLAR & KOŞULLAR",  # Turkish
        "ÖNEMLI ŞARTLAR VE KOŞULLAR",  # Turkish (significant)
        "WARUNKI I ZASADY", "ISTOTNE WARUNKI I ZASADY",  # Polish
        "BETINGELSER OG VILKÅR", "VIKTIGE BETINGELSER OG VILKÅR",  # Norwegian
        "NOTEIKUMI", "BŪTISKIE NOTEIKUMI",  # Latvian
    ]
    end = len(paragraphs)
    for i, para in enumerate(paragraphs[start + 1:], start + 1):
        para_upper = para.upper().strip()
        if "SMS" in para_upper and "OMS" not in para_upper:
            end = i
            break
        if para_upper in tc_exact_headers:
            end = i
            break
    
    for para in paragraphs[start:end]:
        para_stripped = para.strip()
        para_upper = para_stripped.upper()
        
        # Skip the section header itself (check against all localized markers)
        is_header = any(marker in para_upper for marker in markers)
        if is_header:
            # If header has variant, create template now
            if header_variant and not current_template:
                current_template = TemplateContent(
                    variant=header_variant,
                    send_condition=f"ClaimedReward-Template{header_variant}"
                )
                current_field = "title"
            continue
        
        # Check for explicit template variant marker
        variant_match = re.match(r"(?:TEMPLATE|MALL|PÕHI)\s*([A-F])", para_upper)
        if variant_match:
            if current_template:
                section.templates.append(current_template)
            variant = variant_match.group(1)
            current_template = TemplateContent(
                variant=variant,
                send_condition=f"ClaimedReward-Template{variant}"
            )
            current_field = "title"
            continue
        
        # If we hit Title/Body/CTA without a template, create default (A)
        if not current_template and (para_upper in ["TITLE", "TITLE:", "BODY", "BODY:", "CTA", "CTA:"] or
                                      para_upper.startswith("TITLE") or 
                                      para_upper.startswith("BODY") or
                                      para_upper.startswith("CTA")):
            current_template = TemplateContent(
                variant="A",
                send_condition="ClaimedReward-TemplateA"
            )
        
        if current_template:
            # Handle embedded labels (e.g., "Title\nActual title text")
            if para_stripped.upper().startswith("TITLE\n") or para_stripped.upper().startswith("TITLE:\n") or para_stripped.upper().startswith("PEALKIRI\n") or para_stripped.upper().startswith("PEALKIRI:\n"):
                current_field = "title"
                newline_pos = para_stripped.find('\n')
                if newline_pos > 0:
                    rest = para_stripped[newline_pos + 1:].strip()
                    if rest:
                        current_template.title = rest
                continue
            elif para_stripped.upper().startswith("BODY\n") or para_stripped.upper().startswith("BODY:\n"):
                current_field = "body"
                newline_pos = para_stripped.find('\n')
                if newline_pos > 0:
                    rest = para_stripped[newline_pos + 1:].strip()
                    if rest:
                        current_template.body = rest
                continue
            elif para_stripped.upper().startswith("CTA\n") or para_stripped.upper().startswith("CTA:\n"):
                current_field = "cta"
                newline_pos = para_stripped.find('\n')
                if newline_pos > 0:
                    rest = para_stripped[newline_pos + 1:].strip()
                    if rest:
                        current_template.cta = rest
                continue
            
            # Handle standalone field labels
            if para_upper in ("TITLE", "TITLE:", "PEALKIRI", "PEALKIRI:"):
                current_field = "title"
                continue
            elif para_upper.startswith("TITLE:") or para_upper.startswith("TITLE ") or para_upper.startswith("PEALKIRI:") or para_upper.startswith("PEALKIRI "):
                current_field = "title"
                rest = para_stripped.split(None, 1)[1].strip() if len(para_stripped.split(None, 1)) > 1 else ""
                if rest:
                    current_template.title = rest
                continue
            elif para_upper == "BODY" or para_upper == "BODY:":
                current_field = "body"
                continue
            elif para_upper.startswith("BODY:") or para_upper.startswith("BODY "):
                current_field = "body"
                rest = para_stripped[5:].strip()
                if rest:
                    current_template.body = rest
                continue
            elif para_upper in ["CTA", "CTA:", "CALL TO ACTION"]:
                current_field = "cta"
                continue
            elif para_upper.startswith("CTA:") or para_upper.startswith("CTA "):
                current_field = "cta"
                rest = para_stripped[4:].strip()
                if rest:
                    current_template.cta = rest
                continue
            elif current_field and para_stripped:
                current_value = getattr(current_template, current_field) or ""
                new_value = (current_value + "\n" + para_stripped).strip()
                setattr(current_template, current_field, new_value)
    
    # Don't forget the last template
    if current_template:
        section.templates.append(current_template)
    
    return section if section.templates else None


def _parse_sms_section(paragraphs: list[str], section_type: str) -> Optional[SmsSection]:
    """Parse SMS section (Launch or Reminder) with template variants."""
    marker_key = f"{section_type.upper()}_SMS"
    markers = SECTION_MARKERS.get(marker_key, [f"{section_type.upper()} SMS"])
    
    start = _find_section_start(paragraphs, markers)

    # Fallback for table-based docs where SMS table has "SMS" header then
    # standalone "LAUNCH" or "REMINDER" sub-headers (not combined like "LAUNCH SMS").
    if start == -1:
        target = section_type.upper()  # "LAUNCH" or "REMINDER"
        # Estonian equivalents
        et_targets = {"LAUNCH": "LANSSEERIMINE", "REMINDER": "MEELDETULETUS"}
        et_target = et_targets.get(target, "")
        for i, para in enumerate(paragraphs):
            para_upper_stripped = para.upper().strip()
            # Match "SMS", "СМС", or lines starting with "SMS " (e.g., "SMS 18+. sms.%%BrandDomain%%/mensagem")
            is_sms_header = para_upper_stripped in ("SMS", "СМС") or para_upper_stripped.startswith("SMS ") or para_upper_stripped.startswith("СМС ")
            if is_sms_header:
                # Scan ahead for the target sub-header within the SMS block
                for j in range(i + 1, len(paragraphs)):
                    line = paragraphs[j].upper().strip()
                    # Stop if we hit T&C or ADDITIONAL INFO (left the SMS table)
                    if line in ("TAC", "T&C", "T&CS", "ADDITIONAL INFO", "NOTEIKUMI", "TINGIMUSED") or line.startswith("CAMPAIGNWIZARD"):
                        break
                    if line == target or line == et_target:
                        start = j
                        break
                if start != -1:
                    break
    if start == -1:
        return None
    
    # Map section type to SendCondition
    send_condition = "NotOptedIn" if section_type == "Launch" else "JoinedCampaign"
    
    section = SmsSection(section_type=section_type)
    current_template = None
    
    # Find end of SMS section
    # Use only exact T&C section headers (not partial matches that could appear in body text)
    tc_exact_headers = [
        "T&C", "T&CS", "TAC", "TERMS AND CONDITIONS", "SIGNIFICANT TERMS",
        "ΟΡΟΙ ΚΑΙ ΠΡΟΫΠΟΘΕΣΕΙΣ", "ΣΗΜΑΝΤΙΚΟΙ ΟΡΟΙ", "ΠΛΗΡΕΙΣ ΟΡΟΙ",
        "TÉRMINOS Y CONDICIONES", "CONDICIONES IMPORTANTES",
        "TERMOS E CONDIÇÕES", "TERMOS IMPORTANTES",
        "TERMINI E CONDIZIONI",
        "CONDITIONS GÉNÉRALES",
        "ALLGEMEINE GESCHÄFTSBEDINGUNGEN", "AGB",
        "VILKÅR OG BETINGELSER", "ALLMÄNNA VILLKOR",
        "TINGIMUSED", "OLULISED TINGIMUSED", "TÄIELIKUD TINGIMUSED",  # Estonian
        "REEGLID JA TINGIMUSED", "REEGLID",  # Estonian (alt)
        "REGLUR OG SKILYRÐI", "SKILYRÐI",  # Icelandic
        "KÄYTTÖEHDOT", "EHDOT",  # Finnish
        "TERMS & CONDITIONS",  # English variant
        "ŞARTLAR VE KOŞULLAR", "ŞARTLAR & KOŞULLAR",  # Turkish
        "ÖNEMLI ŞARTLAR VE KOŞULLAR",  # Turkish (significant)
        "WARUNKI I ZASADY", "ISTOTNE WARUNKI I ZASADY",  # Polish
        "BETINGELSER OG VILKÅR", "VIKTIGE BETINGELSER OG VILKÅR",  # Norwegian
        "NOTEIKUMI", "BŪTISKIE NOTEIKUMI",  # Latvian
    ]
    end = len(paragraphs)
    for i, para in enumerate(paragraphs[start + 1:], start + 1):
        para_upper = para.upper().strip()
        
        # Check if we hit another major section
        if section_type == "Launch" and ("REMINDER SMS" in para_upper or "REMINDER СМС" in para_upper or "SMS - REMINDER" in para_upper or para_upper in ("REMINDER", "MEELDETULETUS")):
            end = i
            break
        # Only match exact T&C section headers
        if para_upper in tc_exact_headers:
            end = i
            break
    
    for para in paragraphs[start:end]:
        para_stripped = para.strip()
        
        # Strip bullet prefix (• or - or *) if present, for matching
        # This handles Word docs where SMS templates are formatted as list items
        para_for_match = para_stripped
        if para_for_match.startswith("• "):
            para_for_match = para_for_match[2:]
        elif para_for_match.startswith("- ") or para_for_match.startswith("* "):
            para_for_match = para_for_match[2:]
        
        para_upper = para_for_match.upper().strip()
        
        # Check for combined section+variant header (table-based docs)
        # e.g. "LAUNCH SMS - TemplateA", "REMINDER SMS - TemplateB"
        combined_sms_match = re.search(r"(?:TEMPLATE|MALL|PÕHI)\s*([A-F])", para_upper)
        has_sms = "SMS" in para_upper or "СМС" in para_upper
        if combined_sms_match and ("LAUNCH" in para_upper or "REMINDER" in para_upper) and has_sms:
            if current_template:
                section.templates.append(current_template)
            current_template = TemplateContent(
                variant=combined_sms_match.group(1),
                send_condition=send_condition
            )
            continue

        # Skip SMS section headers (e.g., "SMS TEMPLATES", "LAUNCH SMS", "REMINDER SMS", "SMS - LAUNCH")
        # Also handles Cyrillic "СМС" (Russian)
        if has_sms and ("LAUNCH" in para_upper or "REMINDER" in para_upper or para_upper in ("SMS", "СМС") or "TEMPLATES" in para_upper):
            continue

        # Skip standalone sub-headers (table-based docs: "LAUNCH" or "REMINDER" on their own line)
        # Also handles Estonian equivalents
        if para_upper in ("LAUNCH", "REMINDER", "LANSSEERIMINE", "MEELDETULETUS"):
            continue

        # Skip standalone "BODY" labels (table-based docs have [Body, content] rows)
        if para_upper == "BODY" or para_upper == "BODY:":
            continue
        
        # Check for template variant marker with inline body (e.g., "Template A: body content...")
        inline_match = re.match(r"^(?:TEMPLATE|MALL|PÕHI)\s*([A-F])[:：\s]+(.+)$", para_upper)
        if inline_match:
            if current_template:
                section.templates.append(current_template)
            variant = inline_match.group(1)
            # Get the actual body content (not uppercased), use stripped version without bullet
            inline_body_match = re.match(r"^(?:[Tt]emplate|[Mm]all|[Pp]õhi)\s*[A-F][:：\s]+(.+)$", para_for_match)
            if inline_body_match:
                body_content = inline_body_match.group(1)
            else:
                body_content = inline_match.group(2)
            current_template = TemplateContent(
                variant=variant,
                send_condition=send_condition,
                body=body_content
            )
            continue
        
        # Check for template variant marker without inline body (e.g., "Template A" on its own line)
        variant_match = re.match(r"^(?:TEMPLATE|MALL|PÕHI)\s*([A-F])$", para_upper)
        if variant_match:
            if current_template:
                section.templates.append(current_template)
            current_template = TemplateContent(
                variant=variant_match.group(1),
                send_condition=send_condition
            )
            continue
        
        # Also check for standalone letter variants
        if para_upper in TEMPLATE_VARIANTS:
            if current_template:
                section.templates.append(current_template)
            current_template = TemplateContent(
                variant=para_upper,
                send_condition=send_condition
            )
            continue
        
        if current_template and para_stripped:
            # SMS only has body content
            current_body = current_template.body or ""
            current_template.body = (current_body + " " + para_stripped).strip()
            
            # Check if this line ends the SMS (unsubscribe link pattern)
            # e.g., "sms.%%PalantirDomain%%/mc" or similar URL patterns
            if "%%PalantirDomain%%" in para_stripped and "/m" in para_stripped.lower():
                # This template is complete, save it and reset
                section.templates.append(current_template)
                current_template = None
    
    if current_template:
        section.templates.append(current_template)
    
    return section if section.templates else None


def _parse_tc_section(paragraphs: list[str]) -> Optional[TcSection]:
    """Parse Terms & Conditions section."""
    # Use strict matching to avoid matching TC markers in body text
    start = _find_tc_section_start(paragraphs, SECTION_MARKERS["TC"])
    if start == -1:
        return None
    
    section = TcSection()
    current_field = None
    
    # Localized markers for field detection
    significant_markers = [
        "SIGNIFICANT TERMS", "SIGNIFICANT T",  # English
        "SIGNIFICANT TERMS & CONDITIONS",  # Variant
        "SIGNIFICANTTERMS",  # CamelCase (table-based docs)
        "ΣΗΜΑΝΤΙΚΟΙ ΟΡΟΙ", "ΣΗΜΑΝΤΙΚΟΊ ΌΡΟΙ",  # Greek (different accent forms)
        "CONDICIONES IMPORTANTES", "TÉRMINOS IMPORTANTES",  # Spanish
        "TERMOS IMPORTANTES",  # Portuguese
        "TERMINI IMPORTANTI",  # Italian
        "CONDITIONS IMPORTANTES",  # French
        "WICHTIGE BEDINGUNGEN",  # German
        "OLULISED TINGIMUSED",  # Estonian
        "ОСНОВНЫЕ ПРАВИЛА", "ВАЖНЫЕ УСЛОВИЯ",  # Russian
        "TÄRKEÄT EHDOT",  # Finnish
        "VIKTIGE BETINGELSER OG VILKÅR", "VIKTIGE BETINGELSER",  # Norwegian
        "ISTOTNE WARUNKI I ZASADY", "ISTOTNE WARUNKI",  # Polish
        "ÖNEMLI ŞARTLAR VE KOŞULLAR", "ÖNEMLI ŞARTLAR",  # Turkish
        "VIGTIGE BETINGELSER OG VILKÅR", "VIGTIGE BETINGELSER",  # Danish
        "BŪTISKIE NOTEIKUMI",  # Latvian
    ]
    full_terms_markers = [
        "TERMS AND CONDITIONS", "TERMS & CONDITIONS", "FULL TERMS", "T&CS", "T&C",  # English
        "TERMSANDCONDITIONS",  # CamelCase (table-based docs)
        "ΠΛΗΡΕΙΣ ΟΡΟΙ", "ΠΛΉΡΕΙΣ ΌΡΟΙ", "ΟΡΟΙ ΚΑΙ ΠΡΟΫΠΟΘΕΣΕΙΣ",  # Greek
        "TÉRMINOS Y CONDICIONES", "CONDICIONES COMPLETAS",  # Spanish
        "TERMOS E CONDIÇÕES", "TERMOS COMPLETOS",  # Portuguese
        "TERMINI E CONDIZIONI",  # Italian
        "CONDITIONS GÉNÉRALES",  # French
        "ALLGEMEINE GESCHÄFTSBEDINGUNGEN", "AGB",  # German
        "TÄIELIKUD TINGIMUSED", "TINGIMUSED",  # Estonian
        "REGLUR OG SKILYRÐI",  # Icelandic
        "ПОЛНЫЕ ПРАВИЛА", "ПРАВИЛА И УСЛОВИЯ",  # Russian
        "TÄYDELLISET EHDOT", "KÄYTTÖEHDOT",  # Finnish
        "BETINGELSER OG VILKÅR",  # Norwegian
        "WARUNKI I ZASADY",  # Polish
        "ŞARTLAR VE KOŞULLAR", "ŞARTLAR & KOŞULLAR",  # Turkish
        "VILKÅR OG BETINGELSER",  # Danish
        "NOTEIKUMI",  # Latvian
    ]

    # Stop markers: sections that come after T&C
    tc_stop_markers = ["ADDITIONAL INFO", "ADDITIONAL INFORMATION"]
    
    for para in paragraphs[start:]:
        para_stripped = para.strip()
        para_upper = para_stripped.upper()
        
        # Stop at ADDITIONAL INFO section (comes after T&C in table-based docs)
        if any(para_upper.startswith(m) for m in tc_stop_markers):
            break

        # Check for significant terms section
        if any(marker in para_upper for marker in significant_markers):
            current_field = "significant_terms"
        # Check for full terms section
        elif any(marker in para_upper for marker in full_terms_markers):
            current_field = "terms_and_conditions"
        elif current_field and para_stripped:
            current_value = getattr(section, current_field) or ""
            new_value = (current_value + "\n" + para_stripped).strip()
            setattr(section, current_field, new_value)
    
    return section


def parse_documents_from_folder(folder_path: Path) -> list[ParsedDocument]:
    """
    Parse all Word documents in a folder.
    
    Args:
        folder_path: Path to folder containing .docx files
        
    Returns:
        List of ParsedDocument objects
    """
    documents = []
    for docx_file in folder_path.glob("*.docx"):
        # Skip temp files
        if docx_file.name.startswith("~"):
            continue
        try:
            parsed = parse_word_document(docx_file)
            documents.append(parsed)
        except Exception as e:
            print(f"Error parsing {docx_file.name}: {e}")
    
    return documents
