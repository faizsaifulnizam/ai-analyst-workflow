import unittest
from src import guardrails


class DateContract(unittest.TestCase):
    def test_execution_uses_explicit_as_of_date(self):
        result = guardrails.execute_sql('SELECT CURRENT_DATE', as_of='2026-10-04')
        self.assertEqual(result['outcome'], 'ok')
        self.assertEqual(str(result['rows'][0][0]), '2026-10-04')


if __name__ == '__main__':
    unittest.main()
