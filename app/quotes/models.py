from pydantic import BaseModel


class QuoteRequest(BaseModel):
    customer: str

    material: str

    thickness: str

    kitchen_length: float

    island: bool = False

    waterfall: int = 0

    splashback: bool = False

    upstands: bool = False

    postcode: str | None = None