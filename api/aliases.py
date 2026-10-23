from fastapi import APIRouter
from pydantic import BaseModel
from api.db import get_session

router = APIRouter()


class AliasRequest(BaseModel):
    code: str
    number: int
    aliases: str


class AliasResponse(BaseModel):
    uid: str
    aliases: str
    status: str


@router.post("/commit/aliases", response_model=AliasResponse)
async def commit_aliases(req: AliasRequest):
    uid = f"{req.code}_{req.number}"
    clean = " ".join(req.aliases.split()).strip()
    if not clean:
        return AliasResponse(uid=uid, aliases="", status="rejected_empty")
    cypher = """
    MATCH (s:Section {uid: $uid})
    SET s.search_aliases = CASE
        WHEN s.search_aliases IS NULL OR s.search_aliases = '' THEN $aliases
        ELSE s.search_aliases + ' ' + $aliases
    END
    RETURN s.uid AS uid, s.search_aliases AS aliases
    """
    with get_session() as session:
        rec = session.run(cypher, uid=uid, aliases=clean).single()
    if not rec:
        return AliasResponse(uid=uid, aliases="", status="not_found")
    return AliasResponse(uid=rec["uid"], aliases=rec["aliases"], status="ok")
