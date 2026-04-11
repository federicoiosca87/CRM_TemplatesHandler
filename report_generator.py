"""
Audit Report Generator for CMS Template Generator

Generates comprehensive audit reports with:
- Session metadata (document, timestamp, duration, brand, markets)
- Language completeness matrix (missing, invalid, fixed, status)
- Export manifest (files, checksums, capability breakdown)
- Validation rules applied
"""

import hashlib
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
        brand: str,
        template_version: str,
        markets: List[str],
        user_notes: str = "",
    ):
        self.document_name = document_name
        self.upload_timestamp = upload_timestamp
        self.end_timestamp = datetime.now()
        self.duration_seconds = (self.end_timestamp - upload_timestamp).total_seconds()
        self.brand = brand
        self.template_version = template_version
        self.markets = markets
        self.user_notes = user_notes
        
        self.language_statuses: Dict[str, LanguageStatus] = {}
        self.file_manifest: List[FileManifestEntry] = []
        self.validation_violations: List[str] = []
        self.fixes_applied: Dict[str, Dict[str, int]] = {}  # {language: {field: count}}
    
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
    
    def get_session_metadata(self) -> str:
        """Generate session metadata section."""
        lines = [
            "## Session Metadata",
            "",
            f"**Document:** {self.document_name}",
            f"**Upload Time:** {self.upload_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Completion Time:** {self.end_timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Duration:** {int(self.duration_seconds // 60)}m {int(self.duration_seconds % 60)}s",
            f"**Brand:** {self.brand}",
            f"**Template Version:** {self.template_version}",
            f"**Markets Included:** {', '.join(self.markets) if self.markets else 'N/A'}",
        ]
        
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
            "| File | Type | Size | SHA256 |",
            "|------|------|------|--------|",
        ]
        
        sms_count = omscount = tc_count = 0
        total_size = 0
        
        for entry in sorted(self.file_manifest, key=lambda x: x.content_type):
            size_kb = entry.size_bytes / 1024
            checksum_short = entry.checksum_sha256[:8]
            lines.append(
                f"| {entry.filename} | {entry.content_type} | {size_kb:.1f} KB | "
                f"`{checksum_short}...` |"
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
        """Generate summary of fixes applied."""
        if not self.fixes_applied:
            return "## Fixes Applied\n\nNo fixes applied in this session."
        
        lines = ["## Fixes Applied by Language", ""]
        
        for lang in sorted(self.fixes_applied.keys()):
            fields = self.fixes_applied[lang]
            total = sum(fields.values())
            lines.append(f"### {lang}")
            for field, count in sorted(fields.items()):
                lines.append(f"- {field}: {count} placeholder{'' if count == 1 else 's'}")
            lines.append(f"**Total:** {total} placeholder{'s' if total != 1 else ''} fixed")
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
    
    def generate_markdown_report(self) -> str:
        """Generate complete audit report as markdown."""
        sections = [
            "# CMS Template Generator - Audit Report",
            "",
            self.get_session_metadata(),
            "",
            self.get_completeness_matrix(),
            "",
            self.get_export_manifest(),
            "",
            self.get_fixes_summary(),
            "",
            self.get_validation_summary(),
        ]
        
        return "\n".join(sections)


def build_report_from_session(
    document_name: str,
    upload_timestamp: datetime,
    parsed_docs: List[ParsedDocument],
    generated_paths: Dict[str, Path],
    qa_issues: Dict[str, list],
    fixes_applied: Dict[str, Dict[str, int]],
    language_names: Dict[str, str],
    brand: str = "Unknown",
    template_version: str = "1.0",
    markets: Optional[List[str]] = None,
    user_notes: str = "",
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
        brand: Brand name (from config or user input)
        template_version: Template version
        markets: List of market codes
        user_notes: Optional user notes about the generation
    
    Returns:
        Populated AuditReport instance
    """
    report = AuditReport(
        document_name=document_name,
        upload_timestamp=upload_timestamp,
        brand=brand,
        template_version=template_version,
        markets=markets or [],
        user_notes=user_notes,
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
    
    # Build file manifest
    for template_type, path in generated_paths.items():
        for file_path in path.rglob("*"):
            if file_path.is_file():
                report.add_file_to_manifest(str(file_path), template_type)
    
    return report
