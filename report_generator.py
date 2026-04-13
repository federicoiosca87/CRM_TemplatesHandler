"""
Audit Report Generator for CMS Template Generator

Generates comprehensive audit reports with:
- Session metadata (document, timestamp, duration, brand, markets)
- Language completeness matrix (missing, invalid, fixed, status)
- Export manifest (files, checksums, capability breakdown)
- Validation rules applied
"""

import hashlib
import html
import re
import difflib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from word_parser import ParsedDocument


@dataclass
class FileManifestEntry:
    """Single file in the export manifest."""
    filename: str
    size_bytes: int
    checksum_sha256: str
    content_type: str  # "SMS", "OMS", "TC"


@dataclass
class LanguageStatus:
    """Completion status for a single language."""
    language_code: str
    language_name: str
    missing_issues: int = 0
    invalid_issues: int = 0
    fixed_count: int = 0
    
    @property
    def status(self) -> str:
        """Determine readiness status."""
        total_issues = self.missing_issues + self.invalid_issues
        if total_issues == 0:
            return "✅ Ready"
        if self.fixed_count >= total_issues:
            return "✅ Ready"
        if self.fixed_count > 0:
            return "⚠️ Partial"
        return "❌ Blocked"
    
    @property
    def readiness_pct(self) -> int:
        """Percentage of issues fixed."""
        total = self.missing_issues + self.invalid_issues
        if total == 0:
            return 100
        return int((self.fixed_count / total) * 100)


class AuditReport:
    """Complete audit report for a CMS generation session."""
    
    def __init__(
        self,
        document_name: str,
        upload_timestamp: datetime,
        offer_type: str,
        template_version: str,
        markets: List[str],
        user_notes: str = "",
        content_edits: Optional[List[Dict[str, str]]] = None,
        task_type: str = "",
        reward_type: str = "",
        send_conditions: Optional[List[str]] = None,
        variants: Optional[List[str]] = None,
        language_count: int = 0,
    ):
        self.document_name = document_name
        self.upload_timestamp = upload_timestamp
        self.end_timestamp = datetime.now()
        self.duration_seconds = (self.end_timestamp - upload_timestamp).total_seconds()
        self.offer_type = offer_type
        self.template_version = template_version
        self.markets = markets
        self.user_notes = user_notes
        self.content_edits = content_edits or []
        self.task_type = task_type
        self.reward_type = reward_type
        self.send_conditions = send_conditions or []
        self.variants = variants or []
        self.language_count = language_count
        
        self.language_statuses: Dict[str, LanguageStatus] = {}
        self.file_manifest: List[FileManifestEntry] = []
        self.validation_violations: List[str] = []
        self.fixes_applied: Dict[str, Dict[str, int]] = {}  # {language: {field: count}}
        self.fix_details: Dict[str, Dict[str, List[str]]] = {}
    
    def add_language_status(
        self,
        language_code: str,
        language_name: str,
        missing: int,
        invalid: int,
        fixed: int,
    ):
        """Add completion status for a language."""
        self.language_statuses[language_code] = LanguageStatus(
            language_code=language_code,
            language_name=language_name,
            missing_issues=missing,
            invalid_issues=invalid,
            fixed_count=fixed,
        )
    
    def add_file_to_manifest(
        self,
        filepath: str,
        content_type: str,
    ):
        """Add generated file to manifest (calculates size and checksum)."""
        path = Path(filepath)
        
        # Calculate checksum
        sha256_hash = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        
        entry = FileManifestEntry(
            filename=path.name,
            size_bytes=path.stat().st_size,
            checksum_sha256=sha256_hash.hexdigest(),
            content_type=content_type,
        )
        self.file_manifest.append(entry)
    
    def add_validation_violation(self, language: str, field: str, token: str, rule: str):
        """Record a validation rule violation."""
        msg = f"{language} | {field}: `{token}` violates rule '{rule}'"
        self.validation_violations.append(msg)
    
    def add_fixes_applied(self, language: str, field: str, count: int):
        """Track fixes applied per field per language."""
        if language not in self.fixes_applied:
            self.fixes_applied[language] = {}
        self.fixes_applied[language][field] = count

    def add_fix_details(self, language: str, field: str, replacements: List[str]):
        """Track exact replacement pairs for each fixed field."""
        if language not in self.fix_details:
            self.fix_details[language] = {}
        self.fix_details[language][field] = list(replacements or [])
    
    def get_completeness_matrix(self) -> str:
        """Generate markdown table of language completeness."""
        lines = [
            "## Language Completeness Matrix",
            "",
            "| Language | Missing | Invalid | Fixed | Readiness | Status |",
            "|----------|---------|---------|-------|-----------|--------|",
        ]
        
        for lang_code in sorted(self.language_statuses.keys()):
            status = self.language_statuses[lang_code]
            lines.append(
                f"| {status.language_name} ({lang_code}) | "
                f"{status.missing_issues} | {status.invalid_issues} | "
                f"{status.fixed_count} | {status.readiness_pct}% | {status.status} |"
            )
        
        return "\n".join(lines)
    
    def get_offer_configuration(self) -> str:
        """Generate offer configuration summary section."""
        task_reward = f"{self.task_type} / {self.reward_type}" if self.task_type else self.offer_type
        lines = [
            "## Offer Configuration",
            "",
            "| Parameter | Value |",
            "|-----------|-------|",
            f"| **Offer Key** | {self.offer_type} |",
            f"| **Task / Reward** | {task_reward} |",
            f"| **Send Conditions** | {', '.join(self.send_conditions) if self.send_conditions else 'N/A'} |",
            f"| **Variants** | {', '.join(self.variants) if self.variants else 'N/A'} |",
            f"| **Languages** | {self.language_count} |",
            f"| **Markets** | {', '.join(self.markets) if self.markets else 'N/A'} |",
        ]
        return "\n".join(lines)

    def get_session_metadata(self) -> str:
        """Generate session metadata section."""
        lines = [
            "## Session Metadata",
            "",
            f"**Document:** {self.document_name}",
            f"**Upload Time:** {self.upload_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Completion Time:** {self.end_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Duration:** {int(self.duration_seconds // 60)}m {int(self.duration_seconds % 60)}s",
            f"**Offer Type:** {self.offer_type}",
            f"**Markets Included:** {', '.join(self.markets) if self.markets else 'N/A'}",
        ]

        if self.template_version:
            lines.insert(-1, f"**Template Version:** {self.template_version}")
        
        if self.user_notes:
            lines.extend([
                "",
                f"**User Notes:**",
                f"```",
                self.user_notes,
                f"```",
            ])
        
        return "\n".join(lines)
    
    def get_export_manifest(self) -> str:
        """Generate export file manifest section."""
        lines = [
            "## Export Manifest",
            "",
            "| File | Type | Size |",
            "|------|------|------|",
        ]
        
        sms_count = omscount = tc_count = 0
        total_size = 0
        
        for entry in sorted(self.file_manifest, key=lambda x: x.content_type):
            size_kb = entry.size_bytes / 1024
            lines.append(
                f"| {entry.filename} | {entry.content_type} | {size_kb:.1f} KB |"
            )
            
            if entry.content_type == "SMS":
                sms_count += 1
            elif entry.content_type == "OMS":
                omscount += 1
            elif entry.content_type == "TC":
                tc_count += 1
            total_size += entry.size_bytes
        
        lines.extend([
            "",
            f"**Breakdown:** SMS: {sms_count} | OMS: {omscount} | TC: {tc_count}",
            f"**Total Size:** {total_size / 1024:.1f} KB",
        ])
        
        return "\n".join(lines)
    
    def get_fixes_summary(self) -> str:
        """Generate summary of auto-fixes and manual invalid-placeholder corrections."""
        lines = ["## Fixes Applied", ""]

        has_auto = bool(self.fixes_applied)
        manual_fix_rows = [
            e
            for e in self.content_edits
            if e.get("resolved_invalid_placeholders", 0) > 0 or e.get("placeholder_token_delta", 0) > 0
        ]

        if not has_auto and not manual_fix_rows:
            if self.content_edits:
                return (
                    "## Fixes Applied\n\n"
                    "No placeholder fixes detected in this session. "
                    f"{len(self.content_edits)} content edit(s) were captured in the Content Edit Log."
                )
            return "## Fixes Applied\n\nNo placeholder fixes detected in this session."

        if has_auto:
            lines.append("### Auto-fixes (Fix safe actions)")
            lines.append("")
            for lang in sorted(self.fixes_applied.keys()):
                fields = self.fixes_applied[lang]
                total = sum(fields.values())
                lines.append(f"#### {lang}")
                for field, count in sorted(fields.items()):
                    replacement_details = self.fix_details.get(lang, {}).get(field, [])
                    if replacement_details:
                        if len(replacement_details) > 3:
                            details_text = ", ".join(replacement_details[:3]) + f" (+{len(replacement_details) - 3} more)"
                        else:
                            details_text = ", ".join(replacement_details)
                        lines.append(f"- {field}: {count} placeholder{'' if count == 1 else 's'} fixed ({details_text})")
                    else:
                        lines.append(f"- {field}: {count} placeholder{'' if count == 1 else 's'}")
                lines.append(f"**Auto-fix total:** {total} placeholder{'s' if total != 1 else ''}")
                lines.append("")

        if manual_fix_rows:
            lines.append("### Manual corrections")
            lines.append("")
            manual_totals: Dict[str, int] = {}
            manual_token_totals: Dict[str, int] = {}
            for row in manual_fix_rows:
                lang = row.get("language", "Unknown")
                manual_totals[lang] = manual_totals.get(lang, 0) + int(row.get("resolved_invalid_placeholders", 0))
                manual_token_totals[lang] = manual_token_totals.get(lang, 0) + int(row.get("placeholder_token_delta", 0))
            for lang in sorted(manual_totals.keys()):
                invalid_total = manual_totals[lang]
                token_total = manual_token_totals.get(lang, 0)
                lines.append(
                    f"- {lang}: {invalid_total} invalid placeholder{'' if invalid_total == 1 else 's'} resolved, "
                    f"{token_total} placeholder token change{'' if token_total == 1 else 's'} from manual edits"
                )
            lines.append("")

        return "\n".join(lines)
    
    def get_validation_summary(self) -> str:
        """Generate validation rules applied summary."""
        if not self.validation_violations:
            return "## Validation Rules\n\nAll placeholders comply with brand validation rules."
        
        lines = [
            "## Validation Violations",
            "",
            f"Found {len(self.validation_violations)} violation(s):",
            "",
        ]
        
        for violation in self.validation_violations:
            lines.append(f"- {violation}")
        
        return "\n".join(lines)

    def get_content_edit_log(self) -> str:
        """Generate detailed log of content edited in-app during this session."""
        if not self.content_edits:
            return "## Content Edit Log\n\nNo manual content edits were detected in this session."

        def tokenize(text: str) -> List[str]:
            return re.findall(r"\S+|\s+", text or "")

        def clip(text: str, max_len: int = 220) -> str:
            if len(text) <= max_len:
                return text
            return text[: max_len - 3] + "..."

        def render_pair(before_text: str, after_text: str) -> tuple[str, str]:
            before_tokens = tokenize(before_text)
            after_tokens = tokenize(after_text)
            matcher = difflib.SequenceMatcher(a=before_tokens, b=after_tokens)

            before_chunks: List[str] = []
            after_chunks: List[str] = []

            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                a_chunk = "".join(before_tokens[i1:i2])
                b_chunk = "".join(after_tokens[j1:j2])

                if tag == "equal":
                    before_chunks.append(html.escape(a_chunk))
                    after_chunks.append(html.escape(b_chunk))
                elif tag in {"replace", "delete"} and a_chunk:
                    before_chunks.append(
                        f"<span style='background:#ffefbf;color:#6f5607;border:1px dashed #d8b45a;border-radius:4px;padding:0 3px;'>{html.escape(a_chunk)}</span>"
                    )
                if tag in {"replace", "insert"} and b_chunk:
                    after_chunks.append(
                        f"<span style='background:#ffefbf;color:#6f5607;border:1px dashed #d8b45a;border-radius:4px;padding:0 3px;'>{html.escape(b_chunk)}</span>"
                    )

            before_html = clip("".join(before_chunks).replace("\n", "<br>"))
            after_html = clip("".join(after_chunks).replace("\n", "<br>"))
            return before_html, after_html

        lines = [
            "## Content Edit Log",
            "",
            "<table>",
            "<thead><tr><th>Language</th><th>Field</th><th>Before</th><th>After</th></tr></thead>",
            "<tbody>",
        ]

        for edit in self.content_edits:
            before_html, after_html = render_pair(edit.get("before", "") or "", edit.get("after", "") or "")
            lines.append(
                "<tr>"
                f"<td>{html.escape(edit.get('language', ''))}</td>"
                f"<td>{html.escape(edit.get('field', ''))}</td>"
                f"<td>{before_html}</td>"
                f"<td>{after_html}</td>"
                "</tr>"
            )

        lines.extend([
            "</tbody>",
            "</table>",
            "",
            f"**Total edited fields:** {len(self.content_edits)}",
        ])

        return "\n".join(lines)
    
    def generate_markdown_report(self) -> str:
        """Generate complete audit report as markdown."""
        sections = [
            "# CMS Template Generator - Audit Report",
            "",
            self.get_session_metadata(),
            "",
            self.get_offer_configuration(),
            "",
            self.get_completeness_matrix(),
            "",
            self.get_export_manifest(),
            "",
            self.get_fixes_summary(),
            "",
            self.get_content_edit_log(),
            "",
            self.get_validation_summary(),
        ]
        
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # HTML report (Confluence-pasteable)
    # ------------------------------------------------------------------

    def generate_html_report(self) -> str:
        """Generate a self-contained HTML report that can be pasted into Confluence."""

        css = (
            "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
            "color:#172b4d;max-width:960px;margin:2em auto;padding:0 1em;line-height:1.6}"
            "h1{border-bottom:2px solid #0052cc;padding-bottom:.3em}"
            "h2{margin-top:1.8em;border-bottom:1px solid #dfe1e6;padding-bottom:.25em}"
            "h3,h4{margin-top:1.2em}"
            "table{border-collapse:collapse;width:100%;margin:1em 0}"
            "th,td{border:1px solid #dfe1e6;padding:8px 12px;text-align:left}"
            "th{background:#f4f5f7;font-weight:600}"
            "tr:nth-child(even){background:#fafbfc}"
            "code{background:#f4f5f7;padding:2px 4px;border-radius:3px;font-size:0.9em}"
            "pre{background:#f4f5f7;padding:12px;border-radius:3px;overflow-x:auto}"
            ".status-ready{color:#006644;font-weight:600}"
            ".status-blocked{color:#de350b;font-weight:600}"
            ".status-partial{color:#ff8b00;font-weight:600}"
            ".diff-highlight{background:#ffefbf;color:#6f5607;border:1px dashed #d8b45a;"
            "border-radius:4px;padding:0 3px}"
            "strong{font-weight:600}"
        )

        parts: list[str] = [
            "<!DOCTYPE html>",
            "<html><head><meta charset='utf-8'>",
            f"<title>Audit Report – {html.escape(self.offer_type)}</title>",
            f"<style>{css}</style>",
            "</head><body>",
            "<h1>CMS Template Generator – Audit Report</h1>",
            self._html_session_metadata(),
            self._html_offer_configuration(),
            self._html_completeness_matrix(),
            self._html_export_manifest(),
            self._html_fixes_summary(),
            self._html_content_edit_log(),
            self._html_validation_summary(),
            "</body></html>",
        ]
        return "\n".join(parts)

    # --- private HTML helpers ---

    def _html_session_metadata(self) -> str:
        rows = [
            ("Document", html.escape(self.document_name)),
            ("Upload Time", self.upload_timestamp.strftime("%Y-%m-%d %H:%M:%S")),
            ("Completion Time", self.end_timestamp.strftime("%Y-%m-%d %H:%M:%S")),
            ("Duration", f"{int(self.duration_seconds // 60)}m {int(self.duration_seconds % 60)}s"),
            ("Offer Type", html.escape(self.offer_type)),
            ("Markets Included", html.escape(", ".join(self.markets)) if self.markets else "N/A"),
        ]
        if self.template_version:
            rows.insert(-1, ("Template Version", html.escape(self.template_version)))

        lines = ["<h2>Session Metadata</h2>", "<table>"]
        for label, value in rows:
            lines.append(f"<tr><td><strong>{label}</strong></td><td>{value}</td></tr>")
        lines.append("</table>")

        if self.user_notes:
            lines.append(f"<p><strong>User Notes:</strong></p><pre>{html.escape(self.user_notes)}</pre>")
        return "\n".join(lines)

    def _html_offer_configuration(self) -> str:
        task_reward = f"{html.escape(self.task_type)} / {html.escape(self.reward_type)}" if self.task_type else html.escape(self.offer_type)
        rows = [
            ("Offer Key", html.escape(self.offer_type)),
            ("Task / Reward", task_reward),
            ("Send Conditions", html.escape(", ".join(self.send_conditions)) if self.send_conditions else "N/A"),
            ("Variants", html.escape(", ".join(self.variants)) if self.variants else "N/A"),
            ("Languages", str(self.language_count)),
            ("Markets", html.escape(", ".join(self.markets)) if self.markets else "N/A"),
        ]
        lines = ["<h2>Offer Configuration</h2>", "<table>"]
        for label, value in rows:
            lines.append(f"<tr><td><strong>{label}</strong></td><td>{value}</td></tr>")
        lines.append("</table>")
        return "\n".join(lines)

    def _html_completeness_matrix(self) -> str:
        lines = [
            "<h2>Language Completeness Matrix</h2>",
            "<table>",
            "<tr><th>Language</th><th>Missing</th><th>Invalid</th><th>Fixed</th><th>Readiness</th><th>Status</th></tr>",
        ]
        for lang_code in sorted(self.language_statuses.keys()):
            s = self.language_statuses[lang_code]
            if "Ready" in s.status:
                cls = "status-ready"
            elif "Blocked" in s.status:
                cls = "status-blocked"
            else:
                cls = "status-partial"
            lines.append(
                f"<tr><td>{html.escape(s.language_name)} ({html.escape(lang_code)})</td>"
                f"<td>{s.missing_issues}</td><td>{s.invalid_issues}</td>"
                f"<td>{s.fixed_count}</td><td>{s.readiness_pct}%</td>"
                f"<td class='{cls}'>{html.escape(s.status)}</td></tr>"
            )
        lines.append("</table>")
        return "\n".join(lines)

    def _html_export_manifest(self) -> str:
        lines = [
            "<h2>Export Manifest</h2>",
            "<table>",
            "<tr><th>File</th><th>Type</th><th>Size</th></tr>",
        ]
        sms = oms = tc = 0
        total = 0
        for entry in sorted(self.file_manifest, key=lambda x: x.content_type):
            size_kb = entry.size_bytes / 1024
            lines.append(
                f"<tr><td>{html.escape(entry.filename)}</td>"
                f"<td>{html.escape(entry.content_type)}</td>"
                f"<td>{size_kb:.1f} KB</td></tr>"
            )
            if entry.content_type == "SMS":
                sms += 1
            elif entry.content_type == "OMS":
                oms += 1
            elif entry.content_type == "TC":
                tc += 1
            total += entry.size_bytes
        lines.append("</table>")
        lines.append(f"<p><strong>Breakdown:</strong> SMS: {sms} | OMS: {oms} | TC: {tc}<br>")
        lines.append(f"<strong>Total Size:</strong> {total / 1024:.1f} KB</p>")
        return "\n".join(lines)

    def _html_fixes_summary(self) -> str:
        has_auto = bool(self.fixes_applied)
        manual_fix_rows = [
            e for e in self.content_edits
            if e.get("resolved_invalid_placeholders", 0) > 0 or e.get("placeholder_token_delta", 0) > 0
        ]

        if not has_auto and not manual_fix_rows:
            note = "No placeholder fixes detected in this session."
            if self.content_edits:
                note += f" {len(self.content_edits)} content edit(s) were captured in the Content Edit Log."
            return f"<h2>Fixes Applied</h2><p>{note}</p>"

        lines = ["<h2>Fixes Applied</h2>"]

        if has_auto:
            lines.append("<h3>Auto-fixes (Fix safe actions)</h3>")
            for lang in sorted(self.fixes_applied.keys()):
                fields = self.fixes_applied[lang]
                total = sum(fields.values())
                lines.append(f"<h4>{html.escape(lang)}</h4><ul>")
                for field, count in sorted(fields.items()):
                    details = self.fix_details.get(lang, {}).get(field, [])
                    if details:
                        detail_text = ", ".join(details[:3])
                        if len(details) > 3:
                            detail_text += f" (+{len(details) - 3} more)"
                        lines.append(f"<li>{html.escape(field)}: {count} placeholder{'s' if count != 1 else ''} fixed ({html.escape(detail_text)})</li>")
                    else:
                        lines.append(f"<li>{html.escape(field)}: {count} placeholder{'s' if count != 1 else ''}</li>")
                lines.append(f"</ul><p><strong>Auto-fix total:</strong> {total} placeholder{'s' if total != 1 else ''}</p>")

        if manual_fix_rows:
            lines.append("<h3>Manual corrections</h3><ul>")
            manual_totals: Dict[str, int] = {}
            manual_token_totals: Dict[str, int] = {}
            for row in manual_fix_rows:
                lang = row.get("language", "Unknown")
                manual_totals[lang] = manual_totals.get(lang, 0) + int(row.get("resolved_invalid_placeholders", 0))
                manual_token_totals[lang] = manual_token_totals.get(lang, 0) + int(row.get("placeholder_token_delta", 0))
            for lang in sorted(manual_totals.keys()):
                inv = manual_totals[lang]
                tok = manual_token_totals.get(lang, 0)
                lines.append(
                    f"<li>{html.escape(lang)}: {inv} invalid placeholder{'s' if inv != 1 else ''} resolved, "
                    f"{tok} placeholder token change{'s' if tok != 1 else ''} from manual edits</li>"
                )
            lines.append("</ul>")

        return "\n".join(lines)

    def _html_content_edit_log(self) -> str:
        if not self.content_edits:
            return "<h2>Content Edit Log</h2><p>No manual content edits were detected in this session.</p>"

        def tokenize(text: str) -> list[str]:
            return re.findall(r"\S+|\s+", text or "")

        def clip(text: str, max_len: int = 220) -> str:
            return text if len(text) <= max_len else text[:max_len - 3] + "..."

        def render_pair(before_text: str, after_text: str) -> tuple[str, str]:
            before_tokens = tokenize(before_text)
            after_tokens = tokenize(after_text)
            matcher = difflib.SequenceMatcher(a=before_tokens, b=after_tokens)
            before_chunks: list[str] = []
            after_chunks: list[str] = []
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                a_chunk = "".join(before_tokens[i1:i2])
                b_chunk = "".join(after_tokens[j1:j2])
                if tag == "equal":
                    before_chunks.append(html.escape(a_chunk))
                    after_chunks.append(html.escape(b_chunk))
                elif tag in {"replace", "delete"} and a_chunk:
                    before_chunks.append(f"<span class='diff-highlight'>{html.escape(a_chunk)}</span>")
                if tag in {"replace", "insert"} and b_chunk:
                    after_chunks.append(f"<span class='diff-highlight'>{html.escape(b_chunk)}</span>")
            return clip("".join(before_chunks).replace("\n", "<br>")), clip("".join(after_chunks).replace("\n", "<br>"))

        lines = [
            "<h2>Content Edit Log</h2>",
            "<table>",
            "<tr><th>Language</th><th>Field</th><th>Before</th><th>After</th></tr>",
        ]
        for edit in self.content_edits:
            before_html, after_html = render_pair(edit.get("before", "") or "", edit.get("after", "") or "")
            lines.append(
                f"<tr><td>{html.escape(edit.get('language', ''))}</td>"
                f"<td>{html.escape(edit.get('field', ''))}</td>"
                f"<td>{before_html}</td><td>{after_html}</td></tr>"
            )
        lines.append("</table>")
        lines.append(f"<p><strong>Total edited fields:</strong> {len(self.content_edits)}</p>")
        return "\n".join(lines)

    def _html_validation_summary(self) -> str:
        if not self.validation_violations:
            return "<h2>Validation Rules</h2><p>All placeholders comply with brand validation rules.</p>"
        lines = [
            "<h2>Validation Violations</h2>",
            f"<p>Found {len(self.validation_violations)} violation(s):</p><ul>",
        ]
        for v in self.validation_violations:
            lines.append(f"<li>{html.escape(v)}</li>")
        lines.append("</ul>")
        return "\n".join(lines)


def build_report_from_session(
    document_name: str,
    upload_timestamp: datetime,
    parsed_docs: List[ParsedDocument],
    generated_paths: Dict[str, Path],
    qa_issues: Dict[str, list],
    fixes_applied: Dict[str, Dict[str, int]],
    fix_details: Dict[str, Dict[str, List[str]]],
    language_names: Dict[str, str],
    offer_type: str = "Unknown",
    template_version: str = "1.0",
    markets: Optional[List[str]] = None,
    user_notes: str = "",
    content_edits: Optional[List[Dict[str, str]]] = None,
    task_type: str = "",
    reward_type: str = "",
    send_conditions: Optional[List[str]] = None,
    variants: Optional[List[str]] = None,
) -> AuditReport:
    """
    Build complete audit report from session state.
    
    Args:
        document_name: Original document filename
        upload_timestamp: When document was uploaded
        parsed_docs: List of parsed documents by language
        generated_paths: Dict of generated template paths
        qa_issues: Dict of {`language`: [issues]} from QA
        fixes_applied: Dict of {language: {field: count}}
        language_names: Dict of {code: name}
        offer_type: Offer key/type used for generation
        template_version: Template version
        markets: List of market codes
        user_notes: Optional user notes about the generation
        content_edits: Optional list of manual edits captured during this session
    
    Returns:
        Populated AuditReport instance
    """
    report = AuditReport(
        document_name=document_name,
        upload_timestamp=upload_timestamp,
        offer_type=offer_type,
        template_version=template_version,
        markets=markets or [],
        user_notes=user_notes,
        content_edits=content_edits,
        task_type=task_type,
        reward_type=reward_type,
        send_conditions=send_conditions,
        variants=variants,
        language_count=len(parsed_docs),
    )
    
    # Build language completeness matrix
    for doc in parsed_docs:
        lang_name = language_names.get(doc.language_code, doc.language_code)
        issues = qa_issues.get(doc.language_code, [])
        missing = sum(1 for i in issues if i.get("type") == "missing")
        invalid = sum(1 for i in issues if i.get("type") == "invalid")
        fixed = fixes_applied.get(doc.language_code, {})
        fixed_count = sum(fixed.values())
        
        report.add_language_status(
            language_code=doc.language_code,
            language_name=lang_name,
            missing=missing,
            invalid=invalid,
            fixed=fixed_count,
        )
        
        # Add fixes to report
        for field, count in fixed.items():
            report.add_fixes_applied(doc.language_code, field, count)
            report.add_fix_details(doc.language_code, field, fix_details.get(doc.language_code, {}).get(field, []))
    
    # Build file manifest
    for template_type, path in generated_paths.items():
        for file_path in path.rglob("*"):
            if file_path.is_file():
                report.add_file_to_manifest(str(file_path), template_type)
    
    return report
