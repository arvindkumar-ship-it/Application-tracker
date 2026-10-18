from fastapi import APIRouter, Depends, Body, HTTPException
from sqlalchemy import select, insert, update, delete,cast,String
from sqlalchemy.exc import IntegrityError
from app.db import get_session
from app.deps import require_auth
from app.models import vault as v
from app.services import vault_service as svc

router = APIRouter(prefix="/vault", tags=["vault"], dependencies=[Depends(require_auth)])


@router.get("/profile")
async def get_profile(session=Depends(get_session)):
    row = await svc.profile(session)
    await session.commit()
    return row


@router.put("/profile")
async def put_profile(body: dict = Body(...), session=Depends(get_session)):
    row = await svc.profile(session)
    values = svc.clean(v.profile, body)
    if values: await session.execute(update(v.profile).where(v.profile.c.id == row["id"]).values(**values))
    await session.commit()
    return await svc.record(session, v.profile, row["id"])


@router.get("/completeness")
async def get_completeness(session=Depends(get_session)):
    return await svc.completeness(session)


@router.get("/facts")
async def list_facts(parent_type: str | None = None, parent_id: str | None = None, include_superseded:bool=False, session=Depends(get_session)):
    query = select(v.fact).order_by(v.fact.c.created_at)
    if not include_superseded:query=query.where(v.fact.c.superseded_by.is_(None))
    if parent_type: query = query.where(v.fact.c.parent_type == parent_type)
    if parent_id: query = query.where(v.fact.c.parent_id == svc.identifier(parent_id))
    return (await session.execute(query)).mappings().all()


async def parent_exists(session, kind, row_id):
    tables = {"profile": v.profile, "project": v.project, "experience": v.experience, "education": v.education, "achievement": v.achievement, "publication": v.publication, "certification": v.certification, "skill": v.skill}
    if kind not in tables: raise HTTPException(422, "Unknown fact parent type")
    await svc.record(session, tables[kind], row_id)


@router.post("/facts")
async def create_fact(body: dict = Body(...), session=Depends(get_session)):
    values = svc.clean(v.fact, svc.validate_fact(dict(body)))
    await parent_exists(session, values.get("parent_type"), values.get("parent_id"))
    values.update(is_verified_by_user=False, source="user_typed", superseded_by=None)
    row = (await session.execute(insert(v.fact).values(**values).returning(v.fact))).mappings().one()
    await session.commit()
    return row


@router.patch("/facts/{row_id}")
async def edit_fact(row_id: str, body: dict = Body(...), session=Depends(get_session)):
    row = await svc.record(session, v.fact, row_id)
    from app.models.tailoring import tailored_resume
    if (await session.execute(select(tailored_resume.c.id).where(cast(tailored_resume.c.sections_json,String).contains(str(row['id']))).limit(1))).first():
        raise HTTPException(409,'This fact supports a saved resume. Supersede it with a replacement to preserve the original evidence.')
    permitted = {"text", "fact_type", "numeric_values", "technologies"}
    if set(body) - permitted: raise HTTPException(422, "Only fact content can be edited here")
    merged = {key: body.get(key, row[key]) for key in permitted}
    if "text" in body and "numeric_values" not in body: merged["numeric_values"] = svc.numeric_values(body["text"])
    values = svc.clean(v.fact, svc.validate_fact(merged))
    values["is_verified_by_user"] = False
    await session.execute(update(v.fact).where(v.fact.c.id == row["id"]).values(**values))
    await session.commit()
    return await svc.record(session, v.fact, row_id)


@router.post("/facts/{row_id}/verify")
async def verify_fact(row_id: str, session=Depends(get_session)):
    row = await svc.record(session, v.fact, row_id)
    if row["superseded_by"]: raise HTTPException(409, "This fact has been superseded")
    svc.validate_fact(dict(row))
    await session.execute(update(v.fact).where(v.fact.c.id == row["id"]).values(is_verified_by_user=True))
    await session.commit()
    return await svc.record(session, v.fact, row_id)


@router.post("/facts/{row_id}/supersede")
async def supersede_fact(row_id: str, body: dict = Body(...), session=Depends(get_session)):
    old = await svc.record(session, v.fact, row_id, lock=True)
    if old["superseded_by"]: raise HTTPException(409, "Fact already superseded")
    values = {key: old[key] for key in ["parent_type", "parent_id", "fact_type", "technologies"]}
    values.update({key: value for key, value in body.items() if key in {"text", "fact_type", "technologies", "numeric_values"}})
    values.update(is_verified_by_user=False, source="user_typed")
    values = svc.clean(v.fact, svc.validate_fact(values))
    row = (await session.execute(insert(v.fact).values(**values).returning(v.fact))).mappings().one()
    await session.execute(update(v.fact).where(v.fact.c.id == old["id"]).values(superseded_by=row["id"]))
    await session.commit()
    return row


@router.get("/projects/{row_id}/tech")
async def list_tech(row_id: str, session=Depends(get_session)):
    await svc.record(session, v.project, row_id)
    return (await session.execute(select(v.project_tech).where(v.project_tech.c.project_id == svc.identifier(row_id)))).mappings().all()


@router.post("/projects/{row_id}/tech")
async def add_tech(row_id: str, body: dict = Body(...), session=Depends(get_session)):
    await svc.record(session, v.project, row_id)
    values = svc.clean(v.project_tech, {**body, "project_id": row_id})
    if not values.get("technology", "").strip(): raise HTTPException(422, "Technology name is required")
    row = (await session.execute(insert(v.project_tech).values(**values).returning(v.project_tech))).mappings().one()
    await session.commit()
    return row


@router.delete("/projects/{row_id}/tech/{tech_id}")
async def delete_tech(row_id: str, tech_id: str, session=Depends(get_session)):
    row = await svc.record(session, v.project_tech, tech_id)
    if row["project_id"] != svc.identifier(row_id): raise HTTPException(404, "Technology not found")
    await session.execute(delete(v.project_tech).where(v.project_tech.c.id == row["id"]))
    await session.commit()
    return {"ok": True}


@router.post("/projects/{row_id}/generate-facts")
async def generate_facts(row_id: str, session=Depends(get_session)):
    from app.services.fact_builder import build_facts
    return await build_facts(session, row_id)


def resolve(section):
    if section not in svc.TABLES: raise HTTPException(404, "Vault section not found")
    return svc.TABLES[section]


@router.get("/{section}")
async def list_records(section: str, session=Depends(get_session)):
    table = resolve(section)
    if section == "resume-variants":
        await svc.seed_variants(session)
        await session.commit()
    return (await session.execute(select(table).order_by(table.c.created_at))).mappings().all()


@router.post("/{section}")
async def create_record(section: str, body: dict = Body(...), session=Depends(get_session)):
    table = resolve(section)
    if "profile_id" in table.c:
        owner = await svc.profile(session)
        body = {**body, "profile_id": str(owner["id"])}
    values = svc.clean(table, body)
    if section == 'resume-variants':
        validate_layout(values)
        if values.get('is_default'): await session.execute(update(v.resume_variant).values(is_default=False))
    label = "role_title" if section == "experience" else "institution" if section == "education" else "title" if section in {"achievements", "publications"} else "name"
    if not values.get(label): raise HTTPException(422, f"{label.replace('_', ' ')} is required")
    row = (await session.execute(insert(table).values(**values).returning(table))).mappings().one()
    await session.commit()
    return row


@router.get("/{section}/{row_id}")
async def get_record(section: str, row_id: str, session=Depends(get_session)):
    return await svc.record(session, resolve(section), row_id)


@router.patch("/{section}/{row_id}")
@router.put("/{section}/{row_id}")
async def update_record(section: str, row_id: str, body: dict = Body(...), session=Depends(get_session)):
    table = resolve(section)
    row = await svc.record(session, table, row_id)
    values = svc.clean(table, body, set(table.c.keys()) - {"id", "created_at", "updated_at", "profile_id"})
    if section == 'resume-variants':
        validate_layout({**row,**values})
        if values.get('is_default'): await session.execute(update(v.resume_variant).where(v.resume_variant.c.id!=row['id']).values(is_default=False))
    if values: await session.execute(update(table).where(table.c.id == row["id"]).values(**values))
    await session.commit()
    return await svc.record(session, table, row_id)


@router.delete("/{section}/{row_id}")
async def delete_record(section: str, row_id: str, session=Depends(get_session)):
    table = resolve(section)
    row = await svc.record(session, table, row_id)
    parent_type = {"projects": "project", "experience": "experience", "education": "education", "achievements": "achievement", "publications": "publication", "certifications": "certification", "skills": "skill"}.get(section)
    if parent_type:
        facts = (await session.execute(select(v.fact.c.id).where(v.fact.c.parent_id == row["id"], v.fact.c.parent_type == parent_type))).scalars().all()
        if facts: raise HTTPException(409, "This record has facts used for evidence. Keep it for resume traceability.")
    if section == "projects": await session.execute(delete(v.project_tech).where(v.project_tech.c.project_id == row["id"]))
    try:
        await session.execute(delete(table).where(table.c.id == row["id"]))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "This record is referenced by a resume and cannot be deleted") from None
    return {"ok": True}


def validate_layout(values):
    sections=values.get('section_order',[])
    allowed={'summary','skills','experience','projects','education','achievements','publications','certifications'}
    if not sections or set(sections)-allowed or len(sections)!=len(set(sections)):
        raise HTTPException(422,'Choose a nonempty section order without duplicates: '+', '.join(sorted(allowed)))
    categories=values.get('skill_group_order',[])
    if set(categories)-{'language','framework','database','devops','ai_ml','tool','concept','soft'}:
        raise HTTPException(422,'Unknown skill category in the group order')
