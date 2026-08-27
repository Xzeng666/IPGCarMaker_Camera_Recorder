import unittest

from carmaker_recorder.ring_buffer import RingBuffer


class RingBufferIntegrityTests(unittest.TestCase):
    def test_overwrite_is_observable(self):
        rb = RingBuffer[int](2)
        self.assertFalse(rb.push_overwrite(1))
        self.assertFalse(rb.push_overwrite(2))
        self.assertTrue(rb.push_overwrite(3))
        stats = rb.stats()
        self.assertEqual(stats.dropped, 1)
        self.assertEqual(stats.high_watermark, 2)
        self.assertEqual(rb.pop(), 2)
        self.assertEqual(rb.pop(), 3)


if __name__ == "__main__":
    unittest.main()
