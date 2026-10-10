import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src import validate, download, figures


class Publication(unittest.TestCase):
    def test_figures_reject_mixed_receipt_counts_before_render(self):
        import json
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            path=Path(td)/'summary.json'
            summary=json.loads(figures.SUMMARY.read_text())
            summary['totals']['pass_first_try']=99
            path.write_text(json.dumps(summary))
            with patch.object(figures,'SUMMARY',path):
                with self.assertRaises(ValueError): figures.load_receipt()

    def test_final_figure_failure_restores_entire_previous_generation(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root = Path(td); figdir=root/'fig'; imgdir=root/'img'
            figdir.mkdir(); imgdir.mkdir()
            old={d/n:b'old generation' for d in (figdir,imgdir) for n in ('f2_pass_rate.png','f3_failures.png','f2_pass_rate-dark.png','f3_failures-dark.png')}
            for p,data in old.items(): p.write_bytes(data)
            replace=os.replace; failed=False
            def fault(src,dst):
                nonlocal failed
                if Path(dst)==imgdir/'f3_failures-dark.png' and not failed:
                    failed=True; raise OSError('last generation promotion')
                return replace(src,dst)
            with patch.object(figures,'FIGDIR',figdir),patch.object(figures,'IMGDIR',imgdir),patch.object(os,'replace',fault):
                with self.assertRaises(OSError): figures.main()
            self.assertTrue(failed)
            self.assertEqual({p:p.read_bytes() for p in old},old)

    def test_download_late_failure_restores_raw_and_manifest(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root = Path(td)
            raw, manifest = root / 'raw.csv', root / 'pull_manifest.json'
            raw.write_bytes(b'old raw')
            manifest.write_bytes(b'old manifest')
            row = '2017-01,TOWN,4 ROOM,1,ST,01 TO 03,90,Model,2000,80 years,500000\n'
            data = (download.EXPECTED_HEADER + '\n' + row + row.replace('2017-01', '2026-09')).encode()
            replace = os.replace
            failed = False
            def fault(src, dst):
                nonlocal failed
                if Path(dst) == manifest and not failed:
                    failed = True
                    raise OSError('late manifest')
                return replace(src, dst)
            with patch.object(download, 'OUT', raw), patch.object(download, 'MANIFEST', manifest), \
                 patch.object(download, 'ROW_FLOOR', 2), \
                 patch.object(download, 'get', lambda url: b'{"data":{"url":"synthetic"}}' if 'poll-download' in url else data), \
                 patch('sys.argv', ['download', '--force']), patch.object(os, 'replace', fault):
                with self.assertRaises(OSError):
                    download.main()
            self.assertEqual(raw.read_bytes(), b'old raw')
            self.assertEqual(manifest.read_bytes(), b'old manifest')

    def test_figure_late_mirror_failure_restores_previous_pair(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root = Path(td)
            figdir, imgdir = root / 'fig', root / 'img'
            figdir.mkdir(); imgdir.mkdir()
            for p in (figdir / 'x.png', imgdir / 'x.png'):
                p.write_bytes(b'old figure')
            replace = os.replace
            failed = False
            def fault(src, dst):
                nonlocal failed
                if Path(dst) == imgdir / 'x.png' and not failed:
                    failed = True
                    raise OSError('late mirror')
                return replace(src, dst)
            def build():
                fig, ax = figures.plt.subplots()
                ax.plot([1, 2], [2, 3])
                return fig
            with patch.object(figures, 'FIGDIR', figdir), patch.object(figures, 'IMGDIR', imgdir), \
                 patch.object(figures, 'T', figures.LIGHT), patch.object(os, 'replace', fault):
                with self.assertRaises(OSError):
                    figures.render(build, 'x.png')
            for p in (figdir / 'x.png', imgdir / 'x.png'):
                self.assertEqual(p.read_bytes(), b'old figure')

    def test_late_summary_failure_restores_previous_results(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get('AI_WORKFLOW_TEST_TMP')) as td:
            root = Path(td)
            old = {root / 'results.csv': b'previous results', root / 'summary.json': b'previous summary'}
            for p, data in old.items():
                p.write_bytes(data)
            replace = os.replace
            failed = False
            def fault(src, dst):
                nonlocal failed
                if Path(dst).name == 'summary.json' and not failed:
                    failed = True
                    raise OSError('synthetic late promotion failure')
                return replace(src, dst)
            with patch('sys.argv', ['validate', '--outdir', str(root)]), patch.object(os, 'replace', fault):
                with self.assertRaises(OSError):
                    validate.main()
            self.assertTrue(failed)
            self.assertEqual({p: p.read_bytes() for p in old}, old)


if __name__ == '__main__':
    unittest.main()
