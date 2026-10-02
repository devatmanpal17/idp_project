"""Persistent review cards from missed assessment questions; no model calls."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text


def utcnow():
    return datetime.now(timezone.utc)


class MistakeNotebook:
    def __init__(self, engine, lock):
        self.engine, self.lock = engine, lock
        with self.lock, engine.begin() as db:
            db.execute(text('''CREATE TABLE IF NOT EXISTS mistake_reviews (
                id TEXT PRIMARY KEY, attempt_id INTEGER NOT NULL, question_index INTEGER NOT NULL,
                topic TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL,
                due_at TEXT NOT NULL, last_reviewed_at TEXT, review_count INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 0)'''))
            db.execute(text('CREATE INDEX IF NOT EXISTS mistake_reviews_due ON mistake_reviews(due_at,id)'))
            db.execute(text('''CREATE TABLE IF NOT EXISTS learning_migrations (
                name TEXT PRIMARY KEY, completed_at TEXT NOT NULL)'''))
            if not db.execute(text("SELECT 1 FROM learning_migrations WHERE name='mistake-notebook-v1'")).scalar():
                for row in db.execute(text('SELECT id,topic,completed_at,details_json FROM quiz_attempts')).mappings().all():
                    self.capture(db, row['id'], row['topic'], row['completed_at'], json.loads(row['details_json']))
                db.execute(text("INSERT INTO learning_migrations VALUES ('mistake-notebook-v1',:now)"),
                           {'now': utcnow().isoformat()})

    def capture(self, db, attempt_id, topic, completed_at, details):
        for index, detail in enumerate(details):
            if detail.get('is_correct') is not False:
                continue
            if not detail.get('question') or not detail.get('expected_answer'):
                continue  # Older partial telemetry does not contain a reviewable question.
            db.execute(text('''INSERT INTO mistake_reviews
                (id,attempt_id,question_index,topic,detail_json,created_at,due_at)
                VALUES (:id,:attempt,:index,:topic,:detail,:created,:created)
                ON CONFLICT(id) DO NOTHING'''),
                {'id': f'mistake_{attempt_id}_{index}', 'attempt': attempt_id, 'index': index,
                 'topic': topic, 'detail': json.dumps(detail), 'created': completed_at})

    @staticmethod
    def decode(row):
        if row is None:
            return None
        item = dict(row)
        item['detail'] = json.loads(item.pop('detail_json'))
        return item

    def get(self, item_id):
        with self.engine.connect() as db:
            return self.decode(db.execute(text('SELECT * FROM mistake_reviews WHERE id=:id'),
                                          {'id': item_id}).mappings().first())

    def list(self, include_scheduled=False, limit=20, offset=0, now=None):
        timestamp = (now or utcnow()).isoformat()
        where = '' if include_scheduled else 'WHERE due_at<=:now'
        with self.engine.connect() as db:
            rows = db.execute(text(f'''SELECT * FROM mistake_reviews {where}
                ORDER BY due_at,id LIMIT :limit OFFSET :offset'''),
                {'now': timestamp, 'limit': limit, 'offset': offset}).mappings().all()
            counts = db.execute(text('''SELECT COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN due_at<=:now THEN 1 ELSE 0 END),0) AS due,
                COALESCE(SUM(CASE WHEN review_count>0 THEN 1 ELSE 0 END),0) AS reviewed
                FROM mistake_reviews'''), {'now': timestamp}).mappings().one()
        return {'items': [self.decode(row) for row in rows], 'summary': dict(counts),
                'total': counts['total'] if include_scheduled else counts['due'], 'offset': offset,
                'limit': limit, 'server_time': timestamp}

    def review(self, item_id, outcome, version, now=None):
        if outcome not in ('again', 'remembered'):
            raise ValueError('Choose again or remembered.')
        timestamp = now or utcnow()
        with self.lock, self.engine.begin() as db:
            row = db.execute(text('SELECT * FROM mistake_reviews WHERE id=:id'),
                             {'id': item_id}).mappings().first()
            if not row:
                raise LookupError('Review card was not found.')
            if row['version'] != version:
                raise ValueError('This card was already updated. Refresh before reviewing it again.')
            streak = row['streak'] + 1 if outcome == 'remembered' else 0
            delay = timedelta(days=(1, 3, 7, 14, 30)[min(streak - 1, 4)]) if streak else timedelta(minutes=10)
            updated = db.execute(text('''UPDATE mistake_reviews SET due_at=:due,last_reviewed_at=:now,
                review_count=review_count+1,streak=:streak,version=version+1
                WHERE id=:id AND version=:version'''),
                {'due': (timestamp + delay).isoformat(), 'now': timestamp.isoformat(),
                 'streak': streak, 'id': item_id, 'version': version})
            if not updated.rowcount:
                raise ValueError('This card was already updated. Refresh before reviewing it again.')
        return self.get(item_id)
