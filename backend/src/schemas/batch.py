from pydantic import BaseModel,Field
class BatchCreate(BaseModel):
 name:str=Field(min_length=2,max_length=180)
 csv_text:str=Field(min_length=1,max_length=1500000)
 description:str=Field(default="",max_length=2000)
class BatchEdit(BaseModel):
 description:str=Field(max_length=2000)
class BatchImport(BaseModel):
 csv_text:str=Field(min_length=1,max_length=1500000)
 idempotency_key:str|None=Field(default=None,max_length=80)
