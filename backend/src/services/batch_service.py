from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.batch import StatementBatch
from .import_service import import_csv, serialize_import
from .input_records import parse_csv_records

def create(db,body,actor=""):
 # Validate rows before creating the batch so a fully bad upload leaves no empty batch.
 try:parsed=parse_csv_records(body.csv_text)
 except ValueError as error:raise HTTPException(422,str(error))
 if not any(row["parsed"] for row in parsed):raise HTTPException(422,"CSV中没有可写入的合法分录；请修正隔离行后重新导入")
 if db.scalar(select(StatementBatch).where(StatementBatch.name==body.name)):raise HTTPException(409,"对账批次名称已存在")
 batch=StatementBatch(id=str(uuid4()),name=body.name,description=body.description);db.add(batch);db.flush()
 result,rows=import_csv(db,batch.id,body.csv_text,source="initial",actor=actor)
 return batch,result

def append(db,ident,body,actor=""):
 batch=db.get(StatementBatch,ident)
 if batch is None:raise HTTPException(404,"对账批次不存在")
 result,rows=import_csv(db,batch.id,body.csv_text,source="continued",actor=actor,
   idempotency_key=body.idempotency_key)
 return serialize_import(db,result)
