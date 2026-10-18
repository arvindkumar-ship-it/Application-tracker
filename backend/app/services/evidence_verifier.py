import re
from app.services.text_cleaner import normalize_whitespace


def verify_quote(quote, source_text):
    return bool(normalize_whitespace(quote)) and normalize_whitespace(quote).casefold() in normalize_whitespace(source_text).casefold()


def verify_extraction(extraction, source):
    report = {"dropped_fields": [], "fields": {}}
    for key, raw in extraction.items():
        if key in {"multiple_jobs_detected", "titles"}: continue
        items = raw if isinstance(raw, list) else [raw]
        verified = []
        for item in items:
            if not isinstance(item, dict) or item.get("value") is None: continue
            value, evidence = str(item["value"]), item.get("evidence")
            valid = verify_quote(evidence, source)
            if key in {'work_mode','employment_type'}:
                canonical=lambda s:normalize_whitespace(re.sub(r'[_-]',' ',str(s or ''))).casefold()
                valid=valid and canonical(value) in canonical(evidence)
            else:
                valid=valid and verify_quote(value,evidence)
            if "email" in key:
                valid = valid and bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)) and verify_quote(value, source)
            if "url" in key or "website" in key:
                valid = valid and value.startswith(("http://", "https://")) and verify_quote(value, source)
            if key in {"stipend_or_salary_text", "application_deadline_text", "posted_date_text", "experience_required_text", "openings_count_text"}:
                valid = valid and all(token in (evidence or "") for token in re.findall(r"\d+(?:[.,]\d+)*", value))
            if not valid:
                report["dropped_fields"].append(key)
                report["fields"][key] = "evidence_not_found"
            else:
                if "[UNREADABLE]" in (evidence or ""): item["confidence"] = "low"
                verified.append(item)
                report["fields"][key] = "verified"
        extraction[key] = verified if isinstance(raw, list) else verified[0] if verified else {"value": None, "evidence": None, "confidence": "low"}
    return extraction, report
