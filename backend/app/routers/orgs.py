from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.organization import Organization
from app.routers.auth import get_current_org_from_api_key, get_current_org_from_jwt

router = APIRouter(prefix="/orgs", tags=["orgs"])


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str


@router.get("/me", response_model=OrgResponse)
async def get_my_org(org: Organization = Depends(get_current_org_from_jwt)):
    return OrgResponse(id=str(org.id), name=org.name, slug=org.slug, plan=org.plan)
