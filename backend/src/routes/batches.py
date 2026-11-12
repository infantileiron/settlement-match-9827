from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..utils.auth import current,write_user,admin
from ..schemas.batch import BatchCreate,BatchEdit,BatchImport
from ..controllers import batch_controller as controller,common
from ..models.batch import StatementBatch
from ..models.common import serialize
router=APIRouter(prefix="/batches",tags=["batches"])
@router.get("")
def listing(db=Depends(get_db),user=Depends(current)):return controller.list_all(db)
@router.get("/{ident}")
def detail(ident:str,db=Depends(get_db),user=Depends(current)):return controller.detail(db,ident)
@router.get("/{ident}/imports")
def imports(ident:str,db=Depends(get_db),user=Depends(current)):return controller.imports(db,ident)
@router.get("/{ident}/imports/{import_id}")
def import_detail(ident:str,import_id:str,db=Depends(get_db),user=Depends(current)):return controller.import_detail(db,ident,import_id)
@router.post("",status_code=201)
def create(body:BatchCreate,db=Depends(get_db),user=Depends(write_user)):return controller.create(db,body,user)
@router.post("/{ident}/imports",status_code=201)
def append(ident:str,body:BatchImport,db=Depends(get_db),user=Depends(write_user)):return controller.append(db,ident,body,user)
@router.patch("/{ident}")
def edit(ident:str,body:BatchEdit,db=Depends(get_db),user=Depends(write_user)):
 row=common.require(db,StatementBatch,ident);row.description=body.description;db.commit();return serialize(row)
