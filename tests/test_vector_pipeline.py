"""Real SQLite + Chroma integration; deterministic test embeddings, no model quality claims."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine, text
from fastapi import HTTPException
from ml.rag_engine import RAGEngine
from ml.temporal import Caption, Interval
from backend.models import AskRequest, GenerateQuizRequest, SummarizeRequest, RetrieveRequest
from backend.routes import rag as routes


class CountingEmbeddings:
    model = 'deterministic-test-only'
    def __init__(self): self.calls = 0
    def embed(self, texts):
        self.calls += 1
        return [[1.0, 0.0, 0.0] if 'zephyr' in t.lower() else [0.0, 1.0, 0.0] for t in texts]


class VectorPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.db = create_engine(f'sqlite:///{(self.root / "state.db").as_posix()}')
        self.embed = CountingEmbeddings()
        self.rag = RAGEngine(self.root / 'chroma', state_engine=self.db, embeddings=self.embed)
        self.doc = self.rag.vectors.register('https://example.test/video', 'Test', [
            Caption(start_ms=0, end_ms=1000, text='Ordinary opening lesson content.'),
            Caption(start_ms=5000, end_ms=6000, text='Zephyr secret is the copper lantern.')])['document_id']
        for chunk in self.rag.vectors.pending(self.doc):
            self.rag.vectors.embed_chunk(self.doc, chunk['id'])

    def tearDown(self):
        self.db.dispose()
        self.tmp.cleanup()

    def observe(self, intervals, sequence=1):
        return self.rag.vectors.observe(self.doc, 'session-123', sequence,
            [Interval(start_ms=a, end_ms=b) for a,b in intervals], 'rendered-frame')

    def test_sealed_leakage_promotion_and_zero_inference(self):
        self.assertEqual(self.rag.retrieve('zephyr'), [])
        self.observe([(0, 1000), (7000, 8000)])
        self.assertNotIn('Zephyr', str(self.rag.retrieve('zephyr')))
        before = self.embed.calls
        self.observe([(5000, 6000)], 2)
        self.assertEqual(self.embed.calls, before)
        self.assertIn('Zephyr', str(self.rag.retrieve('zephyr', document_id=self.doc)))
        self.rag.vectors.promote(self.doc)
        self.assertEqual(self.rag.count, 2)

    def test_crash_after_upsert_recovers_without_inference_or_duplicates(self):
        def fail(stage):
            if stage == 'after_upsert': raise RuntimeError('injected crash')
        self.rag.vectors.fault_hook = fail
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.observe([(5000, 6000)])
        before = self.embed.calls
        self.rag.vectors.fault_hook = lambda stage: None
        self.rag.vectors.recover()
        self.assertEqual(self.embed.calls, before)
        self.assertEqual(self.rag.count, 1)
        with self.db.connect() as db:
            self.assertEqual(db.execute(text("SELECT promotion_sequence FROM temporal_chunks WHERE state='ACTIVE'")).scalar(), 1)

    def test_all_generation_endpoints_receive_active_only(self):
        observed_contexts = []
        def answer(question, chunks, *args, **kwargs):
            observed_contexts.append(chunks); return 'No evidence.'
        with patch.object(routes, 'rag_engine', self.rag), patch.object(routes.llm_service, 'answer_with_rag', side_effect=answer):
            routes.ask_lesson(AskRequest(question='zephyr secret?', source_type='video', document_id=self.doc,
                                        transcript_context='Zephyr injected bypass text'))
            self.assertEqual(observed_contexts, [[]])
            self.assertEqual(routes.retrieve_chunks(RetrieveRequest(query='zephyr'))['chunks'], [])
            with self.assertRaises(HTTPException):
                routes.generate_quiz(GenerateQuizRequest(topic='Test', source_type='video', document_id=self.doc))
            with self.assertRaises(HTTPException):
                routes.summarize_page(SummarizeRequest(topic='Test', source_type='video', document_id=self.doc))

    def test_revision_deletion_stale_proof_and_normal_pages(self):
        self.observe([(0, 6000)])
        newer = self.rag.vectors.register('https://example.test/video', 'Test', [
            Caption(start_ms=0, end_ms=1000, text='Changed transcript version')])['document_id']
        with self.assertRaises(ValueError): self.observe([(0, 6000)], 2)
        self.assertEqual(self.rag.count, 0)
        self.assertEqual(self.rag.vectors.status(newer)['observed_intervals'], [])
        doc = self.rag.ingest_document('Ordinary webpage content remains searchable.', 'Web', 'Notes')
        self.assertTrue(self.rag.retrieve('Ordinary', document_id=doc['document_id']))
        self.rag.delete_documents([newer, doc['document_id']])
        self.assertEqual(self.rag.count, 0)
