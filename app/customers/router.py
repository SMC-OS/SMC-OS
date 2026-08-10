import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.customers.models import CustomerCreate, CustomerOut
from app.customers.service import customer_service
from app.database.database import get_db

router = APIRouter(
    prefix="/customers", tags=["customers"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[CustomerOut])
def list_customers(limit: int = 20, db: Session = Depends(get_db)):
    return customer_service.list_all(db, limit=limit)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: uuid.UUID, db: Session = Depends(get_db)):
    customer = customer_service.get(db, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(data: CustomerCreate, db: Session = Depends(get_db)):
    return customer_service.create(db, data)
