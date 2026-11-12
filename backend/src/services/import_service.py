import time
import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError,OperationalError
from fastapi import HTTPException
from ..models.item import SettlementItem
from ..models.import_record import ImportRun, ImportRow
from ..models.common import now
from .input_records import parse_csv_records, FIELDS, normalize

# Every imported line finishes as exactly one of these three outcomes, so the
# three counts always add up to the original number of data rows. Content
# conflicts are "quarantined" too, carrying a conflict reason code, because
# they are neither written nor duplicates and must wait for manual checking.
OUTCOMES = ("inserted", "duplicate", "quarantined")


def _canonical(values):
    """Content identity: NFKC/case/space folded party and reference, exact rest."""
    return {
        "side": values["side"],
        "party": normalize(values["party"]),
        "reference": normalize(values["reference"]),
        "amount_cents": int(values["amount_cents"]),
        "currency": values["currency"],
        "booking_date": values["booking_date"],
    }


def _item_values(item):
    return {field: getattr(item, field) for field in FIELDS}


def _same_content(left, right):
    return _canonical(left) == _canonical(right)


def _idempotency_key(key):
    """Only an explicit client key replays a result; re-uploads are classified again."""
    if key is None or not key.strip():
        return None
    key = key.strip()
    if len(key) > 80:
        raise HTTPException(422, "幂等键最多80字符")
    return key


def _row_record(import_id, row, outcome, reason="", reasons=None, item_id=None, existing_item_id=None):
    return ImportRow(
        import_id=import_id,
        line_no=row["line_no"],
        external_id=(row.get("external_id") or None),
        outcome=outcome,
        reason=reason,
        reasons=reasons or [],
        raw_text=row.get("raw_text", ""),
        payload=row.get("parsed"),
        item_id=item_id,
        existing_item_id=existing_item_id,
    )


def _quarantine(records, import_id, row, reason, codes, existing_item_id=None):
    records.append(_row_record(import_id, row, "quarantined", reason, codes, existing_item_id=existing_item_id))


def _classify(import_id, parsed, existing):
    """Classify every row; return (records, pending inserts keyed by external_id).

    A row is compared with the already-saved item of the same external_id in
    the batch (same content -> duplicate, different content -> quarantine as a
    conflict). IDs that do not exist yet are compared within this upload: later
    equal copies are duplicates of the first, while any differing copy holds the
    whole new ID back so no unverified content is written.
    """
    records = []
    candidate = {}
    pending = {}

    for row in parsed:
        values = row["parsed"]
        if values is None:
            _quarantine(records, import_id, row, "；".join(row["errors"]), row["codes"])
            continue
        ident = values["external_id"]
        original = existing.get(ident)
        if original is not None:
            if _same_content(_item_values(original), values):
                records.append(_row_record(import_id, row, "duplicate", "同批同编号内容一致",
                                           ["duplicate_existing"], existing_item_id=original.id))
            else:
                _quarantine(records, import_id, row, "同批同编号内容不一致，留待核对；不覆盖原记录",
                            ["conflict_existing"], existing_item_id=original.id)
            continue
        entry = candidate.get(ident)
        if entry is None:
            item_id = str(uuid.uuid4())
            record = _row_record(import_id, row, "inserted", "", [], item_id=item_id)
            candidate[ident] = {"parsed": values, "item_id": item_id, "record": record,
                                "state": "inserted"}
            pending[ident] = {"parsed": values, "item_id": item_id}
            records.append(record)
            continue
        if entry["state"] == "inserted" and _same_content(entry["parsed"], values):
            records.append(_row_record(import_id, row, "duplicate", "同批同编号内容一致",
                                       ["duplicate_in_upload"], existing_item_id=entry["item_id"]))
            continue
        # Same ID, different content, both new: neither occurrence can be trusted.
        reason = "同批同编号内容不一致，留待核对；不覆盖原记录"
        records.append(_row_record(import_id, row, "quarantined", reason,
                                   ["conflict_in_upload"],
                                   existing_item_id=entry["item_id"]))
        if entry["state"] == "inserted":
            entry["record"].outcome = "quarantined"
            entry["record"].reason = reason
            entry["record"].reasons = ["conflict_in_upload"]
            entry["state"] = "conflict"
            pending.pop(ident, None)
    return records, pending


def _replay(db, batch_id, key):
    """An explicitly supplied idempotency key returns the stored result, not a new write."""
    if key is None:
        return None
    run = db.scalar(
        select(ImportRun).where(ImportRun.batch_id == batch_id, ImportRun.idempotency_key == key)
    )
    if run is None:
        return None
    if run.status != "completed":
        raise HTTPException(409, "相同导入仍在处理中，请稍后查看结果")
    return run, _load_rows(db, run)


def _attempt(db, batch_id, parsed, source, actor, key):
    replayed = _replay(db, batch_id, key)
    if replayed is not None:
        return replayed
    result = ImportRun(
        id=str(uuid.uuid4()), batch_id=batch_id, status="completed", source=source,
        idempotency_key=key, actor=actor or "", total_rows=len(parsed),
    )
    db.add(result)
    db.flush()

    existing = {
        item.external_id: item
        for item in db.scalars(select(SettlementItem).where(SettlementItem.batch_id == batch_id)).all()
    }
    records, pending = _classify(result.id, parsed, existing)
    for ident, entry in pending.items():
        db.add(SettlementItem(id=entry["item_id"], batch_id=batch_id, **entry["parsed"]))
    db.flush()  # unique (batch_id, external_id) catches a concurrent writer here
    db.add_all(records)
    result.inserted_rows = sum(1 for row in records if row.outcome == "inserted")
    result.duplicate_rows = sum(1 for row in records if row.outcome == "duplicate")
    result.quarantined_rows = sum(1 for row in records if row.outcome == "quarantined")
    result.conflict_rows = sum(
        1 for row in records if any("conflict" in reason for reason in (row.reasons or []))
    )
    assert result.inserted_rows + result.duplicate_rows + result.quarantined_rows == result.total_rows
    result.finished_at = now()
    db.commit()
    return result, records


def import_csv(db, batch_id, text, source="continued", actor="", idempotency_key=None):
    """Append valid new rows to an existing batch and isolate every bad row.

    The whole attempt runs in one transaction. A unique (batch_id, external_id)
    index plus an idempotency key on the import attempt make concurrent uploads
    and retries safe: the loser of a race rolls back without writing anything,
    then reclassifies the same rows as duplicate/conflict against the winner.
    """
    key = _idempotency_key(idempotency_key)
    # A retried request with the same key gets the original outcome even if the
    # body was re-sent differently; the key wins over content, so a retry never
    # writes twice. To re-import after fixing a quarantined row, omit the key.
    replayed = _replay(db, batch_id, key)
    if replayed is not None:
        return replayed
    try:
        parsed = parse_csv_records(text)
    except ValueError as error:
        raise HTTPException(422, str(error))
    if not parsed:
        raise HTTPException(422, "CSV须含1至500条分录")
    for attempt in range(3):
        try:
            return _attempt(db, batch_id, parsed, source, actor, key)
        except IntegrityError:
            # A competing import took the same key or external_id. Roll back the
            # whole attempt (nothing was written), then replay the winner (same
            # key) or reclassify every row against the rows it wrote.
            db.rollback()
            replayed = _replay(db, batch_id, key)
            if replayed is not None:
                return replayed
            db.expire_all()
        except OperationalError as error:
            # SQLite raises this for its table lock; MySQL deadlocks appear the
            # same way. Retry briefly before asking the caller to try again.
            db.rollback()
            if attempt == 2:raise HTTPException(409,f"导入未完成，请稍后重试（{str(error)[:80]}）")
            time.sleep(0.05*(attempt+1))
    raise HTTPException(409, "并发导入冲突，本次未写入任何分录；请重试或使用相同幂等键查看结果")


def _load_rows(db, import_run):
    return db.scalars(
        select(ImportRow).where(ImportRow.import_id == import_run.id).order_by(ImportRow.line_no)
    ).all()


def serialize_import(db, import_run):
    rows = _load_rows(db, import_run)
    totals = {
        "total_rows": import_run.total_rows,
        "inserted": import_run.inserted_rows,
        "duplicate": import_run.duplicate_rows,
        "quarantined": import_run.quarantined_rows,
        # Informational subset of quarantined; not part of the three-way sum.
        "conflict": import_run.conflict_rows,
    }
    three_way = totals["inserted"] + totals["duplicate"] + totals["quarantined"]
    return {
        "id": import_run.id,
        "batch_id": import_run.batch_id,
        "status": import_run.status,
        "source": import_run.source,
        "actor": import_run.actor,
        "created_at": import_run.created_at.isoformat() + "Z" if import_run.created_at else None,
        "finished_at": import_run.finished_at.isoformat() + "Z" if import_run.finished_at else None,
        "totals": totals,
        "totals_check": {
            "complete": three_way == import_run.total_rows,
            "inserted_plus_duplicate_plus_quarantined": three_way,
            "total_rows": import_run.total_rows,
        },
        "rows": [row.to_dict() for row in rows],
    }
