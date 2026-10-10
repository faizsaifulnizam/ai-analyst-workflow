import unittest
from datetime import datetime
from src.fingerprint import fingerprint
from src.validate import classify


class TypedMatching(unittest.TestCase):
    def test_classifier_honors_versioned_reference(self):
        n, h = fingerprint([('A', 'B')], version=2)
        self.assertEqual(classify({'outcome': 'ok', 'rows': [('A', 'B')]},
                                 {'rows': n, 'sha256': h, 'version': 2})[0], '')
        self.assertEqual(classify({'outcome': 'ok', 'rows': [('A\x1fB',)]},
                                 {'rows': n, 'sha256': h, 'version': 2})[0], 'value_mismatch')

    def test_v2_distinguishes_shape_null_time_and_large_integer(self):
        pairs = [([('A\x1fB',)], [('A', 'B')]),
                 ([(None,)], [('null',)]),
                 ([(datetime(2026, 1, 1, 1),)], [(datetime(2026, 1, 1, 2),)]),
                 ([(9007199254740992,)], [(9007199254740993,)])]
        for a, b in pairs:
            self.assertNotEqual(fingerprint(a, version=2), fingerprint(b, version=2))
        self.assertEqual(fingerprint([(42,)], version=2), fingerprint([(42.0,)], version=2))


if __name__ == '__main__':
    unittest.main()
