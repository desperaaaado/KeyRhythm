from __future__ import annotations

import unittest

from keyrhythm.resources import executable_path, resource_path


class ResourceTests(unittest.TestCase):
    def test_source_tree_resolves_vendored_release_resources(self) -> None:
        self.assertTrue(resource_path("bin/ffmpeg.exe").is_file())
        self.assertTrue(resource_path("bin/libfluidsynth-3.dll").is_file())
        self.assertTrue(resource_path("assets/soundfonts/default.sf2").is_file())
        self.assertEqual(executable_path("ffmpeg.exe"), str(resource_path("bin/ffmpeg.exe")))


if __name__ == "__main__":
    unittest.main()
