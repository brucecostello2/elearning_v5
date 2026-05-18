(excerpt)from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.deps import get_db
from app.services.retention_service import RetentionService
from app.services.tier_migration_service import TierMigrationService
from app.schemas.phase4_schemas import (
    RetentionPolicyCreate, RetentionPolicyOut,
    TierOverrideRequest, TierOverrideResponse,
)

router = APIRouter(prefix="/retention", tags=["retention"])

@router.get("/policies", response_model=list[RetentionPolicyOut])
def list_policies(db: Session = Depends(get_db)):
    from app.models.retention import RetentionPolicy
    return db.query(RetentionPolicy).all()

@router.post("/policies", response_model=RetentionPolicyOut)
def create_policy(body: RetentionPolicyCreate, db: Session = Depends(get_db)):
    from app.models.retention import RetentionPolicy
    pol = RetentionPolicy(**body.model_dump())
    db.add(pol)
    db.commit()
    db.refresh(pol)
    return pol

@router.post("/override-tier", response_model=TierOverrideResponse)
def override_tier(body: TierOverrideRequest, db: Session = Depends(get_db)):
    svc = TierMigrationService(db)
    results = svc.bulk_migrate(body.output_ids, body.target_tier,
                               triggered_by="api:manual")
    return TierOverrideResponse(**results)

@router.post("/run-lifecycle")
def trigger_lifecycle(db: Session = Depends(get_db)):
    svc = RetentionService(db)
    return svc.run_lifecycle()
