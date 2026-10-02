"""Check SQL evidence state even when index mutations fail; guard model publication."""
from sqlalchemy import text


def _rows(rag, chunks):
    ids = {item['chunk_id'] for item in chunks}
    if not ids:
        return {}, {}
    params = {f'id{i}': value for i, value in enumerate(sorted(ids))}
    placeholders = ','.join(':' + key for key in params)
    with rag.vectors.engine.connect() as db:
        scoped = {row['chroma_id']: row for row in db.execute(text(f"""SELECT c.*,r.revision
            FROM scoped_chunks c JOIN scoped_revisions r
            ON r.learner_key=c.learner_key AND r.video_key=c.video_key
            WHERE c.chroma_id IN ({placeholders})"""), params).mappings()}
        temporal = {row['id']: row for row in db.execute(text(f"""SELECT c.*,d.revision,
            d.state AS document_state FROM temporal_chunks c
            JOIN media_documents d ON d.id=c.document_id
            WHERE c.id IN ({placeholders})"""), params).mappings()}
    return scoped, temporal


def _active(rag, chunk, scoped, temporal, quiz_id=None):
    chunk_id = chunk['chunk_id']
    owned = False
    if quiz_id:
        with rag.vectors.engine.connect() as db:
            owners = set(db.execute(text('''SELECT l.quiz_id FROM evidence_lease_chunks c
                JOIN evidence_leases l ON l.id=c.lease_id
                WHERE c.chunk_id=:id AND l.state='OPEN' '''), {'id': chunk_id}).scalars())
        owned = owners == {quiz_id}
    if chunk_id in scoped:
        row = scoped[chunk_id]
        return (((row['state'] == 'ACTIVE' and row['demote_refcount'] == 0)
                 or (row['state'] == 'DEMOTED' and owned))
                and row['embed_model'] == rag.model_version and row['content'] == chunk['snippet'])
    if chunk_id in temporal:
        row = temporal[chunk_id]
        return ((row['state'] == 'ACTIVE' or (row['state'] == 'DEMOTED' and owned))
                and row['document_state'] == 'CURRENT'
                and row['model_version'] == rag.model_version and row['text'] == chunk['snippet'])
    return True  # Ordinary page/document vectors have no temporal SQL row.


def active_chunks(rag, chunks):
    scoped, temporal = _rows(rag, chunks)
    return [chunk for chunk in chunks if _active(rag, chunk, scoped, temporal)]


def snapshot(rag, chunks, quiz_id=None):
    """Call under the RAG lock at retrieval and immediately before publication."""
    scoped, temporal = _rows(rag, chunks)
    signatures = []
    ordinary = [item['chunk_id'] for item in chunks
                if item['chunk_id'] not in scoped and item['chunk_id'] not in temporal]
    documents = {}
    if ordinary:
        result = rag.collection.get(ids=ordinary, include=['documents', 'metadatas'])
        documents = {key: (content, meta or {}) for key, content, meta
                     in zip(result['ids'], result['documents'], result['metadatas'])}
    for chunk in chunks:
        key = chunk['chunk_id']
        if not _active(rag, chunk, scoped, temporal, quiz_id):
            raise ValueError('Source evidence changed or became locked during generation; retry after the quiz or recapture.')
        if key in scoped:
            row = scoped[key]
            signature = ('scoped', key, row['revision'], row['embed_model'])
        elif key in temporal:
            row = temporal[key]
            signature = ('temporal', key, row['revision'], row['model_version'])
        else:
            content, meta = documents.get(key, (None, {}))
            if content != chunk['snippet'] or meta.get('model_version') != rag.model_version:
                raise ValueError('Source evidence changed during generation; recapture and retry.')
            signature = ('document', key, content, meta['model_version'])
        signatures.append(signature)
    return tuple(signatures)


def validate(rag, chunks, original):
    if snapshot(rag, chunks) != original:
        raise ValueError('Source revision changed during generation; recapture and retry.')
