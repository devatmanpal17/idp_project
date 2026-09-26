"""Keep validated quiz slots; ask the model to replace only missing/invalid items."""
import json
import logging
from .metrics import metrics


def repair_questions(count, generate, validate, max_attempts=3):
    if count < 1:
        raise ValueError('At least one question is required.')
    accepted = [None] * count
    errors = []
    for attempt in range(max_attempts):
        missing = [i for i, value in enumerate(accepted) if value is None]
        if not missing:
            return accepted
        metrics.add('quiz_generation_calls')
        if attempt:
            metrics.add('quiz_repair_slots', len(missing))
        raw = generate(len(missing), [q for q in accepted if q is not None], errors)
        errors = []
        try:
            data = json.loads(raw)
            candidates = data.get('questions') if isinstance(data, dict) else None
            if not isinstance(candidates, list) or len(candidates) != len(missing):
                raise ValueError(f'Expected exactly {len(missing)} replacement questions.')
        except (ValueError, TypeError) as exc:
            errors.append(str(exc)[:500])
            metrics.add('quiz_invalid_envelopes')
            continue
        for slot, candidate in zip(missing, candidates):
            try:
                accepted[slot] = validate(candidate, [q for q in accepted if q is not None])
                metrics.add('quiz_validated_questions')
            except (ValueError, TypeError) as exc:
                detail = '; '.join(f"{item['loc']}: {item['msg']}" for item in exc.errors()) if hasattr(exc, 'errors') else str(exc)
                errors.append(f'Slot {slot + 1}: {detail[:500]}')
                logging.getLogger(__name__).warning('quiz_repair_rejection slot=%s reason=%s', slot + 1, detail[:500])
                metrics.add('quiz_rejected_questions')
    if all(question is not None for question in accepted):
        return accepted
    raise ValueError('Quiz still contains invalid or missing questions after three attempts. ' + '; '.join(errors))
