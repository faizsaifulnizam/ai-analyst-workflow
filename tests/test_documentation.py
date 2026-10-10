import unittest
from html.parser import HTMLParser
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


class Surface(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]; self.h1=0; self.main=0; self.bad=[]
    def handle_starttag(self, tag, attrs):
        if tag == 'h1': self.h1 += 1
        if tag == 'main': self.main += 1
        if tag == 'figcaption' and 'figure' not in self.stack: self.bad.append(tag)
        if tag not in ('img','meta','link','source','br'): self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack)-1-self.stack[::-1].index(tag)]


class Docs(unittest.TestCase):
    def test_page_has_landmark_heading_and_valid_caption_ancestry(self):
        parser=Surface(); parser.feed((ROOT/'docs/index.html').read_text())
        self.assertEqual((parser.h1, parser.main, parser.bad), (1, 1, []))
    def test_leads_describe_reference_disagreement_not_five_semantic_errors(self):
        for name in ('README.md', 'docs/index.html', 'docs/decision_memo.md', 'docs/failure_catalogue.md'):
            text=(ROOT/name).read_text()
            self.assertIn('two semantic', text, name)
            self.assertNotIn('wrong values for every month after a gap', text, name)
    def test_historical_audit_script_gap_is_disclosed(self):
        self.assertIn('not available', (ROOT/'docs/audit.md').read_text())


if __name__ == '__main__': unittest.main()
