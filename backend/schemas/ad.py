Python
from pydantic import BaseModel

class AdRequest(BaseModel):
    category: str
    product_name: str

class AdResponse(BaseModel):
    status: str
    message: str
    generated_copy: str