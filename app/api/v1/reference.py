from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.models import StorageSite
from app.db.session import get_db
from app.deps import Caller, get_caller, require_admin
from app.errors import ApiError, field_error
from app.repositories import reference as ref_repo
from app.schemas.reference import ProductOut, ReferenceOut, StorageSiteIn, StorageSiteOut
from app.services import engines

router = APIRouter(tags=["reference"])


@router.get("/reference", response_model=ReferenceOut, summary="Products, markets, locations, storage sites")
def reference(caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    try:
        products = [ProductOut(code=p.code, label_fr=p.label_fr, label_en=p.label_en, source_note=p.source_note)
                    for p in engines.products().values()]
    except ApiError:  # engine not installed yet: the form still works
        products = [ProductOut(code="tomato", label_fr="Tomate", label_en="Tomato",
                               source_note="engine not installed: parameters unavailable")]
    return ReferenceOut(products=products, locations=ref_repo.locations(db), markets=ref_repo.markets(db),
                        storage_sites=ref_repo.storage_sites(db, caller.organization_id))


@router.post("/storage-sites", response_model=StorageSiteOut, status_code=status.HTTP_201_CREATED,
             summary="Add a storage site to the organization (admin)")
def create_site(data: StorageSiteIn, caller: Caller = Depends(require_admin), db: Session = Depends(get_db)):
    if ref_repo.location(db, data.location_id) is None:
        raise field_error("location_id", "unknown", "unknown location")
    return ref_repo.save(db, StorageSite(organization_id=caller.organization_id, **data.model_dump()))
