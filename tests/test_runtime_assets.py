from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.runtime_assets import RUNTIME_PATHS, install_bundle, sha256


class RuntimeBundleTests(unittest.TestCase):
    def make_bundle(self, root: Path, *, corrupt_member=False):
        archive_path = root / 'runtime.zip'
        manifest = {'files': []}
        with zipfile.ZipFile(archive_path, 'w') as archive:
            for index, name in enumerate(RUNTIME_PATHS):
                payload = f'fixture-{index}'.encode()
                manifest['files'].append({'path': name, 'sha256': hashlib.sha256(payload).hexdigest()})
                archive.writestr(name, b'tampered' if corrupt_member and index == 3 else payload)
            archive.writestr('../outside.txt', b'must not be extracted')
        manifest['runtime_bundle'] = {'sha256': sha256(archive_path)}
        return archive_path, manifest

    def test_installs_allowlisted_files_without_extracting_other_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, manifest = self.make_bundle(root)
            project = root / 'project'
            install_bundle(project, manifest, archive)
            for index, name in enumerate(RUNTIME_PATHS):
                self.assertEqual((project / name).read_bytes(), f'fixture-{index}'.encode())
            self.assertFalse((root / 'outside.txt').exists())

    def test_archive_checksum_failure_leaves_existing_file_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, manifest = self.make_bundle(root)
            destination = root / 'project' / RUNTIME_PATHS[0]
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b'existing')
            manifest['runtime_bundle']['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'bundle SHA-256'):
                install_bundle(root / 'project', manifest, archive)
            self.assertEqual(destination.read_bytes(), b'existing')

    def test_member_checksum_failure_is_detected_before_any_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, manifest = self.make_bundle(root, corrupt_member=True)
            with self.assertRaisesRegex(ValueError, 'file SHA-256'):
                install_bundle(root / 'project', manifest, archive)
            self.assertFalse((root / 'project').exists())


if __name__ == '__main__':
    unittest.main()
