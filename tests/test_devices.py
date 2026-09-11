from __future__ import annotations

import unittest

from keyrhythm.audio.devices import resolve_output_device


class _SoundDeviceFake:
    default = type("Default", (), {"device": [0, 0]})()
    devices = [
        {"name": "Speakers", "hostapi": 0, "max_output_channels": 2, "default_low_output_latency": 0.09, "default_samplerate": 44100},
        {"name": "Speakers", "hostapi": 1, "max_output_channels": 2, "default_low_output_latency": 0.003, "default_samplerate": 48000},
    ]
    apis = [{"name": "MME"}, {"name": "Windows WASAPI"}]

    @classmethod
    def query_devices(cls, index=None):
        return cls.devices[index] if index is not None else cls.devices

    @classmethod
    def query_hostapis(cls):
        return cls.apis

    @staticmethod
    def check_output_settings(**_kwargs):
        return None


class DeviceTests(unittest.TestCase):
    def test_prefers_wasapi_variant_of_default_hardware(self) -> None:
        self.assertEqual(resolve_output_device(_SoundDeviceFake, None), 1)


if __name__ == "__main__":
    unittest.main()

