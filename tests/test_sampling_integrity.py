import unittest

from carmaker_recorder.sampling import PeriodicSimTimeSampler


class SamplingIntegrityTests(unittest.TestCase):
    def _count(self, input_hz: float, output_hz: float, seconds: float) -> int:
        sampler = PeriodicSimTimeSampler(output_hz)
        frames = int(round(input_hz * seconds)) + 1
        return sum(sampler.should_sample(i / input_hz) for i in range(frames))

    def test_30_fps_to_30_hz_keeps_every_frame(self):
        self.assertEqual(self._count(30, 30, 1.0), 31)

    def test_60_fps_to_10_hz(self):
        self.assertEqual(self._count(60, 10, 2.0), 21)

    def test_30_fps_to_7_5_hz(self):
        self.assertEqual(self._count(30, 7.5, 4.0), 31)

    def test_small_timestamp_jitter_does_not_collapse_schedule(self):
        sampler = PeriodicSimTimeSampler(30)
        times = [0.0]
        for i in range(1, 31):
            jitter = 2e-7 if i % 2 else -2e-7
            times.append(i / 30 + jitter)
        self.assertEqual(sum(sampler.should_sample(t) for t in times), 31)


if __name__ == "__main__":
    unittest.main()
