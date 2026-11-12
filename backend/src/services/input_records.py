import csv,io,re,unicodedata
from datetime import date
from ..constants.enums import MAX_ITEM_CENTS
FIELDS=["external_id","side","party","reference","amount_cents","currency","booking_date"]
MAX_IMPORT_ROWS=500

def normalize(value):return " ".join(unicodedata.normalize("NFKC",value).strip().casefold().split())
def validate_date(value):
 try:
  if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",value):raise ValueError()
  return date.fromisoformat(value).isoformat()
 except Exception:raise ValueError("日期须为有效YYYY-MM-DD")

def _read(text):
 """Yield (line_no, raw_text, cells) for every non-blank CSV record.

 line_no is the 1-based physical line where the record starts; the header is
 line 1. quoted multiline records keep their original source lines.
 """
 lines=text.splitlines()
 reader=csv.reader(io.StringIO(text))
 try:header=next(reader)
 except StopIteration:raise ValueError("CSV须含表头及1至500条分录")
 except csv.Error as e:raise ValueError(f"CSV无法解析：{e}")
 header=[cell.strip().lstrip("\ufeff") for cell in header]
 missing=[field for field in FIELDS if field not in header]
 if missing:raise ValueError("CSV须含完整列，且为1至500条分录")
 if len(header)!=len(set(header)):raise ValueError("CSV表头含重复列")
 records=[];previous=reader.line_num
 try:
  for cells in reader:
   start=previous+1;end=reader.line_num;previous=end
   raw="\n".join(lines[start-1:end]) if start<=end and start-1<len(lines) else ""
   if not raw.strip():continue
   records.append((start,raw,cells))
 except csv.Error as e:raise ValueError(f"CSV无法解析：{e}")
 if not records:raise ValueError("CSV须含1至500条分录")
 if len(records)>MAX_IMPORT_ROWS:raise ValueError(f"单次导入最多{MAX_IMPORT_ROWS}条分录")
 return header,records

def _validate(cells,header,index,raw,line_no):
 """Validate one record in isolation, returning parsed values or reasons."""
 values={field:(cells[index[field]] if index[field]<len(cells) else "") for field in FIELDS}
 errors=[];codes=[]
 if len(cells)>len(header):
  errors.append(f"列数{len(cells)}多于表头{len(header)}")
  codes.append("column_mismatch")
 ident=(values.get("external_id") or "").strip()
 if not ident:errors.append("分录ID为空")
 elif len(ident)>80:errors.append("分录ID超过80字符")
 side=(values.get("side") or "").strip()
 if side not in ["milestone","receipt"]:errors.append("方向须为milestone或receipt")
 party=(values.get("party") or "").strip()
 if not party:errors.append("往来方为空")
 elif len(party)>160:errors.append("往来方超过160字符")
 reference=(values.get("reference") or "").strip()
 if len(reference)>100:errors.append("委托引用超过100字符")
 currency=(values.get("currency") or "").strip()
 if currency!="CNY":errors.append("币种仅接受CNY")
 raw_amount=(values.get("amount_cents") or "").strip()
 amount=None
 if not re.fullmatch(r"[0-9]+",raw_amount):
  errors.append(f"金额“{raw_amount}”须为正整数分，不接受小数、负值或科学计数法")
  codes.append("invalid_amount")
 else:
  amount=int(raw_amount)
  if not 0<amount<=MAX_ITEM_CENTS:
   errors.append("金额分超出允许范围")
   codes.append("amount_out_of_range")
 booking_date=None
 raw_date=(values.get("booking_date") or "").strip()
 try:booking_date=validate_date(raw_date)
 except ValueError as e:
  errors.append(str(e))
  codes.append("invalid_date")
 parsed=None
 if not errors:
  parsed={"external_id":ident,"side":side,"party":party,"reference":reference,"amount_cents":amount,"currency":"CNY","booking_date":booking_date}
 return {"line_no":line_no,"raw_text":raw,"external_id":ident or None,"parsed":parsed,"errors":errors,"codes":codes}

def parse_csv_records(text):
 header,records=_read(text)
 index={field:header.index(field) for field in FIELDS}
 return [_validate(cells,header,index,raw,line_no) for line_no,raw,cells in records]

def parse_csv(text):
 rows=parse_csv_records(text)
 for row in rows:
  if row["errors"]:raise ValueError(f"第{row['line_no']}行："+"；".join(row["errors"]))
 return [row["parsed"] for row in rows]
