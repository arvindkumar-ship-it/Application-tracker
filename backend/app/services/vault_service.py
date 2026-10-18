import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, insert, update, delete, Enum, Date, DateTime, Integer, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from app.models import vault as v

TABLES = {"education": v.education, "experience": v.experience, "projects": v.project, "achievements": v.achievement, "publications": v.publication, "certifications": v.certification, "skills": v.skill, "resume-variants": v.resume_variant}


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Invalid record ID") from None


def clean(table, body, allowed=None):
    if not isinstance(body, dict):
        raise HTTPException(422, "Expected an object")
    permitted = set(allowed) if allowed is not None else set(table.c.keys()) - {"id", "created_at", "updated_at"}
    unknown = set(body) - permitted
    if unknown:
        raise HTTPException(422, "Unknown or read-only fields: " + ", ".join(sorted(unknown)))
    result = {}
    for key, value in body.items():
        column = table.c[key]
        kind = column.type
        if value is None or value == "" and not isinstance(kind, (ARRAY, JSONB)):
            if not column.nullable:
                raise HTTPException(422, f"{key.replace('_', ' ')} is required")
            result[key] = None
            continue
        try:
            if isinstance(kind, Enum):
                if value not in kind.enums:
                    raise ValueError()
            elif isinstance(kind, UUID):
                value = identifier(value)
            elif isinstance(kind, DateTime):
                value = datetime.fromisoformat(value) if isinstance(value, str) else value
            elif isinstance(kind, Date):
                value = date.fromisoformat(value) if isinstance(value, str) else value
            elif isinstance(kind, Boolean):
                if not isinstance(value, bool):
                    raise ValueError()
            elif isinstance(kind, Integer):
                if isinstance(value, bool): raise ValueError()
                value = int(value)
                if key == 'visibility_priority' and not 1<=value<=5: raise ValueError()
                if key in {'team_size','max_projects','max_bullets_per_project','max_bullets_per_experience'} and value<1: raise ValueError()
            elif isinstance(kind, Numeric):
                value = Decimal(str(value))
            elif isinstance(kind, ARRAY):
                if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                    raise ValueError()
                value = list(dict.fromkeys(x.strip() for x in value if x.strip()))
            elif isinstance(kind, JSONB):
                if not isinstance(value, (dict, list)):
                    raise ValueError()
            elif not isinstance(value, str) or len(value) > 100_000:
                raise ValueError()
        except (ValueError, TypeError, ArithmeticError):
            raise HTTPException(422, f"Invalid value for {key.replace('_', ' ')}") from None
        result[key] = value
    return result


async def record(session, table, row_id, lock=False):
    query = select(table).where(table.c.id == identifier(row_id))
    if lock: query = query.with_for_update()
    row = (await session.execute(query)).mappings().first()
    if not row: raise HTTPException(404, "Record not found")
    return dict(row)


async def profile(session):
    row = (await session.execute(select(v.profile))).mappings().first()
    if row: return dict(row)
    return dict((await session.execute(insert(v.profile).values().returning(v.profile))).mappings().one())


async def seed_variants(session):
    # Serializes concurrent initial requests without creating duplicate layouts.
    from sqlalchemy import text
    await session.execute(text("SELECT pg_advisory_xact_lock(71236001)"))
    if (await session.execute(select(v.resume_variant.c.id).limit(1))).first(): return
    for i, name in enumerate(["Agentic AI / Security", "Backend", "Applied ML", "AI Reliability", "General"]):
        await session.execute(insert(v.resume_variant).values(name=name, section_order=["summary", "skills", "experience", "projects", "education", "achievements", "publications", "certifications"], skill_group_order=["language", "framework", "database", "devops", "ai_ml", "tool", "concept", "soft"], max_projects=3, max_bullets_per_project=3, max_bullets_per_experience=3, is_default=i == 4))


def numeric_values(text):
    return [{"value": x, "unit": "", "context": text} for x in dict.fromkeys(re.findall(r"\d+(?:[.,]\d+)*(?:%|\+)?", text))]


def validate_fact(body):
    text = str(body.get("text", "")).strip()
    if not text: raise HTTPException(422, "A fact needs a single, specific claim")
    if len(text.split()) > 120: raise HTTPException(422, "Split this description into shorter atomic facts")
    body["text"] = text
    values = body.get("numeric_values", numeric_values(text))
    if not isinstance(values, list) or any(not isinstance(x, dict) or "value" not in x for x in values):
        raise HTTPException(422, "numeric_values must be a list of value, unit and context objects")
    for token in numeric_values(text):
        if not any(str(item["value"]) == token["value"] for item in values):
            raise HTTPException(422, "Record every number exactly in numeric_values")
    body["numeric_values"] = values
    return body


async def completeness(session):
    facts = (await session.execute(select(v.fact).where(v.fact.c.superseded_by.is_(None)))).mappings().all()
    result = []
    for kind, table in [("project", v.project), ("experience", v.experience)]:
        for row in (await session.execute(select(table))).mappings():
            related = [f for f in facts if f["parent_id"] == row["id"] and f["parent_type"] == kind]
            verified = [f for f in related if f["is_verified_by_user"]]
            result.append({"id": row["id"], "parent_type": kind, "name": row.get("name") or row.get("role_title") or "Untitled", "fact_count": len(related), "verified_count": len(verified), "has_metrics": any(f["numeric_values"] for f in verified), "missing_fields": [field for field in (["problem_statement", "solution_overview", "outcomes"] if kind == "project" else ["company", "role_title", "description_raw"]) if not row[field]]})
    return result
