"""BCF 2.1 subset export. See docs/architecture/bcf.md for scope."""
from __future__ import annotations
import io, logging, re, uuid, zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree as ET
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.bim import BimElement
from app.models.document import Document, DocumentRevision
from app.models.validation import ValidationIssue, ValidationRun

log = logging.getLogger("bimguard.bcf")
_IFC_GUID_RE = re.compile(r"^[0-9A-Za-z_$]{22}$")

def _is_ifc_guid(v: str) -> bool:
    return bool(_IFC_GUID_RE.match(v or ""))

def _stable_guid(ns: str, name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{ns}:{name}"))

def _aware(dt):
    return dt.replace(tzinfo=UTC) if dt and dt.tzinfo is None else dt

def _version_xml() -> bytes:
    r = ET.Element("Version", {"VersionId": "2.1"})
    ET.SubElement(r, "DetailedVersion").text = "2.1"
    return ET.tostring(r, encoding="utf-8", xml_declaration=True)

def _desc(issue: ValidationIssue) -> str:
    p = []
    if issue.document_number: p.append(f"Document: {issue.document_number}")
    if issue.element_tag: p.append(f"Element: {issue.element_tag}")
    p.append(issue.message)
    if issue.recommended_action: p.append(f"Recommended action: {issue.recommended_action}")
    return "\n\n".join(x for x in p if x)

def _markup_xml(issue: ValidationIssue, run: ValidationRun) -> bytes:
    root = ET.Element("Markup")
    status = "Closed" if issue.status == "acknowledged" else "Open"
    created = _aware(run.created_at or datetime.now(UTC)).isoformat()
    modified = _aware(issue.acknowledged_at).isoformat() if issue.acknowledged_at else created
    author = run.created_by_name or "BIMGuard"
    topic = ET.SubElement(root, "Topic", {"Guid": str(issue.id), "TopicType": "Issue", "TopicStatus": status})
    ET.SubElement(topic, "Title").text = f"{issue.severity}: {issue.title}"
    ET.SubElement(topic, "Priority").text = issue.severity.capitalize()
    ET.SubElement(topic, "CreationDate").text = created
    ET.SubElement(topic, "CreationAuthor").text = author
    ET.SubElement(topic, "ModifiedDate").text = modified
    ET.SubElement(topic, "ModifiedAuthor").text = author
    ET.SubElement(topic, "Description").text = _desc(issue)
    labels = ET.SubElement(topic, "Labels")
    ET.SubElement(labels, "Label").text = issue.rule_id
    ET.SubElement(labels, "Label").text = issue.severity
    if issue.document_number: ET.SubElement(labels, "Label").text = issue.document_number
    if issue.status == "acknowledged":
        c = ET.SubElement(topic, "Comment", {"Guid": _stable_guid("comment", str(issue.id))})
        ET.SubElement(c, "Date").text = modified
        ET.SubElement(c, "Author").text = issue.acknowledged_by_name or "unknown"
        ET.SubElement(c, "Comment").text = issue.acknowledgement_note or "(acknowledged)"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

def _viewpoint_xml(ifc_guid: str) -> bytes:
    r = ET.Element("VisualizationInfo", {"Guid": _stable_guid("vp", ifc_guid)})
    c = ET.SubElement(r, "Components")
    sel = ET.SubElement(c, "Selection")
    ET.SubElement(sel, "Component", {"IfcGuid": ifc_guid})
    ET.SubElement(c, "Visibility", {"DefaultVisibility": "true"})
    return ET.tostring(r, encoding="utf-8", xml_declaration=True)

def _resolve_guid(db: Session, issue: ValidationIssue) -> str | None:
    if not issue.document_id or not issue.element_tag: return None
    doc = db.get(Document, issue.document_id)
    if not doc or doc.current_revision_number is None: return None
    rev = db.scalar(select(DocumentRevision).where(
        DocumentRevision.document_id == doc.id,
        DocumentRevision.revision_number == doc.current_revision_number))
    if not rev: return None
    el = db.scalar(select(BimElement).where(
        BimElement.revision_id == rev.id, BimElement.tag == issue.element_tag))
    return el.guid if el and _is_ifc_guid(el.guid) else None

_SEV = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

def build_bcf(db: Session, run: ValidationRun) -> bytes:
    issues = list(db.scalars(select(ValidationIssue).where(ValidationIssue.run_id == run.id)))
    issues.sort(key=lambda i: (_SEV.get(i.severity, 99), i.document_number or "", i.rule_id, i.id))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bcf.version", _version_xml())
        for issue in issues:
            zf.writestr(f"{issue.id}/markup.bcf", _markup_xml(issue, run))
            guid = _resolve_guid(db, issue)
            if guid:
                zf.writestr(f"{issue.id}/viewpoint.bcfv", _viewpoint_xml(guid))
    return buf.getvalue()