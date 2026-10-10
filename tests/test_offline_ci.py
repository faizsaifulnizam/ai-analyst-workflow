import subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class OfflineCI(unittest.TestCase):
    def test_runner_rejects_empty_and_skipped_suites(self):
        path=ROOT/'tests/offline_ci.py'
        self.assertTrue(path.exists(), 'dependency-backed offline runner missing')
        import importlib.util
        spec=importlib.util.spec_from_file_location('offline_ci',path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with self.assertRaises(RuntimeError): module.run_suite(unittest.TestSuite())
        class Skipped(unittest.TestCase):
            @unittest.skip('canary')
            def test_skip(self): pass
        with self.assertRaises(RuntimeError): module.run_suite(unittest.defaultTestLoader.loadTestsFromTestCase(Skipped))
