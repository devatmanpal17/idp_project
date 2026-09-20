import unittest
from pydantic import ValidationError
from ml.temporal import Caption, Interval, covered, merge_intervals, temporal_chunks, watermark


class TemporalTests(unittest.TestCase):
    def test_merge_seek_rewind_and_watermark(self):
        values = merge_intervals([Interval(start_ms=a, end_ms=b) for a, b in
                                  [(0, 100), (500, 700), (50, 200), (200, 250)]])
        self.assertEqual(values, [[0, 250], [500, 700]])
        self.assertEqual(watermark(values), 250)
        self.assertFalse(covered(250, 501, values))

    def test_invalid_intervals(self):
        for a, b in [(-1, 10), (10, 0), (0, 0), (float('nan'), 1), (0, float('inf'))]:
            with self.assertRaises(ValidationError):
                Interval(start_ms=a, end_ms=b)

    def test_rolling_punctuation_duplicates_order_and_seek(self):
        cues = [Caption(start_ms=a, end_ms=b, text=t) for a, b, t in [
            (0, 1000, 'TCP uses three way'), (500, 1500, 'TCP uses three way handshake to'),
            (1000, 2000, 'three way handshake to establish connection.'),
            (1000, 2000, 'three way handshake to establish connection.'),
            (9000, 10000, 'TCP uses three way')]]
        chunks, metrics = temporal_chunks(list(reversed(cues)))
        self.assertEqual([c['text'] for c in chunks],
                         ['TCP uses three way', 'handshake to', 'establish connection.', 'TCP uses three way'])
        self.assertLess(metrics['deduplicated_bytes'], metrics['raw_caption_bytes'])
