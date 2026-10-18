import re
from sqlalchemy import select, insert
from app.models import vault as v
from app.services.vault_service import record, numeric_values


async def build_facts(session, project_id):
    project = await record(session, v.project, project_id)
    source = "\n".join(project[k] or "" for k in ["one_liner", "problem_statement", "solution_overview", "architecture_notes", "challenges_and_solutions", "outcomes"])
    tech = (await session.execute(select(v.project_tech.c.technology).where(v.project_tech.c.project_id == project["id"]))).scalars().all()
    existing = set((await session.execute(select(v.fact.c.text).where(v.fact.c.parent_id == project["id"]))).scalars())
    rows = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", source):
        sentence = sentence.strip(" \t•-")
        if not sentence or sentence in existing: continue
        # Exact source sentences are candidates only. Nothing becomes usable until confirmed.
        values = numeric_values(sentence)
        related = [t for t in tech if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", sentence, re.I)]
        row = (await session.execute(insert(v.fact).values(parent_type="project", parent_id=project["id"], text=sentence, fact_type="metric" if values else "technology_usage" if related else "action", numeric_values=values, technologies=related, source="derived_from_description", is_verified_by_user=False).returning(v.fact))).mappings().one()
        rows.append(row)
        existing.add(sentence)
    await session.commit()
    return {"facts": rows, "method": "exact_source_sentences", "message": "Exact source sentences were split into unverified candidates. Review each claim before confirming."}
