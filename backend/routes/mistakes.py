"""Missed-question review queue that respects current quiz evidence holds."""
from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import text

from ml import rag_engine
from ml.analytics import quiz_analytics
from ..models import ReviewMistakeRequest

router = APIRouter()


def _held_ids():
    with rag_engine.vectors.engine.connect() as db:
        return set(db.execute(text('''SELECT c.chunk_id FROM evidence_lease_chunks c
            JOIN evidence_leases l ON l.id=c.lease_id WHERE l.state='OPEN' ''')).scalars())


def _public(item, held):
    locked = bool(set(item['detail'].get('citations', [])) & held)
    result = {key: item[key] for key in ('id', 'topic', 'created_at', 'due_at', 'last_reviewed_at',
                                      'review_count', 'streak', 'version')}
    result['locked'] = locked
    if not locked:
        detail = item['detail']
        result.update(question=detail['question'], given_answer=detail.get('given_answer', ''),
                      expected_answer=detail['expected_answer'], explanation=detail.get('explanation', ''),
                      bloom_level=detail.get('bloom_level', ''), citation_count=len(detail.get('citations', [])))
    return result


@router.get('/api/learning/mistakes')
def list_mistakes(include_scheduled: bool = False, limit: int = Query(20, ge=1, le=100),
                  offset: int = Query(0, ge=0)):
    with rag_engine._lock, quiz_analytics._lock:
        result = quiz_analytics.mistakes.list(include_scheduled, limit, offset)
        held = _held_ids()
        result['items'] = [_public(item, held) for item in result['items']]
        return result


@router.post('/api/learning/mistakes/{item_id}/review')
def review_mistake(request: ReviewMistakeRequest,
                   item_id: str = Path(..., pattern=r'^mistake_[1-9][0-9]*_[0-9]+$')):
    with rag_engine._lock, quiz_analytics._lock:
        item = quiz_analytics.mistakes.get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail='Review card was not found.')
        held = _held_ids()
        if _public(item, held)['locked']:
            raise HTTPException(status_code=409, detail='This material is held by an open quiz. Submit or abandon the quiz first.')
        try:
            updated = quiz_analytics.mistakes.review(item_id, request.outcome, request.version)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _public(updated, held)
