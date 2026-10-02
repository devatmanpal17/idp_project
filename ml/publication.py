"""Private evidence proofs for durable model outputs, separate from public responses."""
from contextlib import contextmanager
from contextvars import ContextVar

from .evidence_snapshot import snapshot

_collector = ContextVar('evidence_publication_collector', default=None)


@contextmanager
def capture():
    records = []
    token = _collector.set(records)
    try:
        yield records
    finally:
        _collector.reset(token)


def record(rag, chunks, signature):
    records = _collector.get()
    if records is not None:
        records.append({'chunks': [{'chunk_id': c['chunk_id'], 'snippet': c['snippet']} for c in chunks],
                        'signature': [list(row) for row in signature]})


def record_cached(rag, key, scope):
    if _collector.get() is None:
        return
    from sqlalchemy import text
    import json
    with rag.vectors.engine.connect() as db:
        encoded = db.execute(text('SELECT retrieved_ids_json FROM answer_cache WHERE key=:key AND scope=:scope'),
                             {'key': key, 'scope': scope}).scalar_one()
        chunks = []
        for chunk_id in json.loads(encoded):
            content = db.execute(text('SELECT content FROM scoped_chunks WHERE chroma_id=:id'),
                                 {'id': chunk_id}).scalar()
            if content is None:
                content = db.execute(text('SELECT text FROM temporal_chunks WHERE id=:id'),
                                     {'id': chunk_id}).scalar()
            if content is None:
                raise ValueError('Cached source evidence is no longer available.')
            chunks.append({'chunk_id': chunk_id, 'snippet': content})
    record(rag, chunks, snapshot(rag, chunks))


def validate_records(rag, records, quiz_id=None):
    for item in records:
        current = [list(row) for row in snapshot(rag, item['chunks'], quiz_id=quiz_id)]
        if current != item['signature']:
            raise ValueError('Stored output belongs to changed source evidence; recapture and retry.')
