"""Offline boundary canaries through both real provider payload builders."""
import unittest
from unittest.mock import patch
from src import generate


class RetryPrivacy(unittest.TestCase):
    def test_provider_payload_never_includes_engine_diagnostic(self):
        for provider in ('gemini', 'groq'):
            bodies = []
            def transport(url, payload=None, **kwargs):
                bodies.append(payload)
                if provider == 'groq':
                    return {'choices': [{'message': {'content': 'SELECT 1'}}]}
                return {'candidates': [{'content': {'parts': [{'text': 'SELECT 1'}]}}]}
            with patch.object(generate, 'http_json', transport), patch.object(generate.time, 'sleep'):
                generate.ask(provider, 'synthetic-key', 'synthetic-model', 'Count rows',
                             feedback='sql_error: ROW_ONLY_CANARY_719', prior_sql='SELECT 1')
            self.assertNotIn('ROW_ONLY_CANARY_719', str(bodies))
            self.assertIn('SELECT 1', str(bodies))


if __name__ == '__main__':
    unittest.main()
