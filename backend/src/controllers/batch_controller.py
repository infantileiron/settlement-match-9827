from sqlalchemy import select
from fastapi import HTTPException
from ..models.import_record import ImportRun
from ..services import batch_service
from ..services.import_service import serialize_import
from ..models.batch import StatementBatch
from ..models.common import serialize
from .common import listing,require

def list_all(db):return listing(db,StatementBatch)
def detail(db,ident):return serialize(require(db,StatementBatch,ident))
def create(db,body,user=None):
 batch,result=batch_service.create(db,body,user.email if user else "")
 # Keep the batch fields at the top level for existing clients, and attach the row-level result.
 return {**serialize(batch),"import":serialize_import(db,result)}
def append(db,ident,body,user=None):
 return batch_service.append(db,ident,body,user.email if user else "")
def imports(db,batch_id):
 if db.get(StatementBatch,batch_id) is None:raise HTTPException(404,"对账批次不存在")
 rows=db.scalars(select(ImportRun).where(ImportRun.batch_id==batch_id).order_by(ImportRun.created_at.desc()).limit(50)).all()
 return [serialize_import(db,row) for row in rows]
def import_detail(db,batch_id,import_id):
 row=db.get(ImportRun,import_id)
 if row is None or row.batch_id!=batch_id:raise HTTPException(404,"导入记录不存在")
 return serialize_import(db,row)
