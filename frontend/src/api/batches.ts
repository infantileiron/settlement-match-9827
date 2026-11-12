import {request} from "./client";
export const fetchBatches=()=>request("/batches");
export const createBatches=(body:unknown)=>request("/batches","POST",body);
export const appendBatchImport=(batchId:string,body:unknown)=>request("/batches/"+encodeURIComponent(batchId)+"/imports","POST",body);
export const fetchBatchImports=(batchId:string)=>request("/batches/"+encodeURIComponent(batchId)+"/imports");
export const fetchBatchImport=(batchId:string,importId:string)=>request("/batches/"+encodeURIComponent(batchId)+"/imports/"+encodeURIComponent(importId));
