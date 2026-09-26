"""SQL job ledger. Restart resumes checkpointed chunks, never the MV3 message channel."""
import json
import time
import uuid
from threading import RLock
from sqlalchemy import text
from .metrics import metrics


class JobStore:
    def __init__(self, engine):
        self.engine, self.lock = engine, RLock()
        with engine.begin() as db:
            db.execute(text("""CREATE TABLE IF NOT EXISTS persistent_jobs (
                id TEXT PRIMARY KEY, operation TEXT NOT NULL, payload_json TEXT NOT NULL,
                document_id TEXT, status TEXT NOT NULL, stage TEXT NOT NULL,
                checkpoint_json TEXT NOT NULL, result_json TEXT, error TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, resume_count INTEGER NOT NULL DEFAULT 0)"""))

    def create(self, operation, payload, request_id=None):
        job_id = request_id or uuid.uuid4().hex
        with self.lock, self.engine.begin() as db:
            old = db.execute(text('SELECT * FROM persistent_jobs WHERE id=:id'), {'id': job_id}).mappings().first()
            encoded = json.dumps(payload, sort_keys=True)
            if old:
                if old['operation'] != operation or old['payload_json'] != encoded:
                    raise ValueError('Request ID already used for a different operation.')
                return job_id, False
            db.execute(text("""INSERT INTO persistent_jobs
                (id,operation,payload_json,document_id,status,stage,checkpoint_json,created_at,updated_at)
                VALUES (:id,:operation,:payload,:doc,'queued','CAPTURED','{}',:now,:now)"""),
                dict(id=job_id, operation=operation, payload=encoded, doc=payload.get('document_id'), now=time.time()))
        return job_id, True

    def get(self, job_id, private=False):
        with self.engine.connect() as db:
            row = db.execute(text('SELECT * FROM persistent_jobs WHERE id=:id'), {'id': job_id}).mappings().first()
        if not row: return None
        result = {key: row[key] for key in ['operation','status','stage','error','created_at','updated_at','attempts','resume_count']}
        result.update(job_id=row['id'], checkpoint=json.loads(row['checkpoint_json']))
        if not private and 'result' in result['checkpoint']:
            result['checkpoint'] = {'output_validated': True}
        if row['result_json']: result['result'] = json.loads(row['result_json'])
        if private: result['payload'] = json.loads(row['payload_json'])
        return result

    def claim(self, job_id):
        with self.lock, self.engine.begin() as db:
            return db.execute(text("""UPDATE persistent_jobs SET status='running',attempts=attempts+1,
                updated_at=:now WHERE id=:id AND status='queued'"""), {'id': job_id, 'now': time.time()}).rowcount == 1

    def checkpoint(self, job_id, stage, payload):
        with self.engine.begin() as db:
            db.execute(text("""UPDATE persistent_jobs SET stage=:stage,checkpoint_json=:payload,
                updated_at=:now WHERE id=:id AND status='running'"""),
                {'id': job_id, 'stage': stage, 'payload': json.dumps(payload), 'now': time.time()})
        metrics.add('job_checkpoints_total')

    def finish(self, job_id, result=None, error=None):
        with self.engine.begin() as db:
            db.execute(text("""UPDATE persistent_jobs SET status=:status,stage=:stage,
                result_json=:result,error=:error,updated_at=:now WHERE id=:id AND status='running'"""),
                {'id': job_id, 'status': 'failed' if error is not None else 'succeeded', 'stage': 'FAILED' if error is not None else 'COMPLETE',
                 'result': json.dumps(result) if result is not None else None, 'error': error, 'now': time.time()})

    def recover(self):
        with self.lock, self.engine.begin() as db:
            count = db.execute(text("""UPDATE persistent_jobs SET status='queued',resume_count=resume_count+1
                ,updated_at=:now WHERE status='running'"""), {'now': time.time()}).rowcount
            ids = db.execute(text("""SELECT id FROM persistent_jobs WHERE status='queued'
                ORDER BY CASE WHEN operation='speculate' THEN 1 ELSE 0 END,created_at""")).scalars().all()
        metrics.add('jobs_resumed', count)
        return ids

    def cancel_documents(self, document_ids):
        with self.engine.begin() as db:
            for doc in document_ids:
                db.execute(text("""UPDATE persistent_jobs SET status='failed',stage='FAILED',
                    payload_json='{}',checkpoint_json='{}',result_json=NULL,error='Document deleted',updated_at=:now
                    WHERE document_id=:doc"""), {'doc': doc, 'now': time.time()})

    def queue_depth(self):
        with self.engine.connect() as db:
            return db.execute(text("SELECT COUNT(*) FROM persistent_jobs WHERE status IN ('queued','running')")).scalar()

    def diagnostics(self):
        with self.engine.connect() as db:
            return [dict(row) for row in db.execute(text("""SELECT id,operation,status,stage,
                attempts,resume_count,updated_at FROM persistent_jobs ORDER BY updated_at DESC LIMIT 100""")).mappings()]
