import gzip
import json
from pathlib import Path
import tempfile
import unittest
import importlib.util

_export_path = Path(__file__).resolve().parents[3] / 'scripts' / 'export_vercel_demo.py'
_spec = importlib.util.spec_from_file_location('afterfire_vercel_export', _export_path)
_export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_export)
Bundle, sanitize, require_before_after = _export.Bundle, _export.sanitize, _export.require_before_after


class ExportTests(unittest.TestCase):
    def test_before_after_requires_real_exported_frames_for_both_indices(self):
        event={'id':'candidate','start_date':'2021-08-01','end_date':'2021-08-03'}
        frames=[{'index':index,'date':date,'period_end':end,'value':.2,'assets':[{'name':index+date+'.png'}]}
                for index in ('NDVI','EVI') for date,end in [('2021-07-01','2021-07-16'),('2021-08-13','2021-08-28')]]
        assets={o['assets'][0]['name']:'/exported.png' for o in frames}
        require_before_after({'observations':frames},event,assets)
        for observations,exported in [([],assets),(frames,{}),(frames[:2],assets),
                                      ([dict(o,value=None) for o in frames],assets),
                                      ([dict(o,period_end='2021-08-02') for o in frames],assets)]:
            with self.assertRaises(ValueError):require_before_after({'observations':observations},event,exported)
    def test_science_and_nulls_are_exact(self):
        value={'value':-.012345678901234,'qa':2048,'version':'061','missing':None,'provenance':['https://lpdaac.usgs.gov/products/mod13q1v061/']}
        self.assertEqual(value,sanitize(value))
    def test_authentic_optical_pair_must_be_exported_and_bracket_event(self):
        event={'id':'candidate','start_date':'2021-08-01','end_date':'2021-08-03'}
        result={'observations':[],'high_resolution':{'before':{'id':'b','date':'2021-07-20'},'after':{'id':'a','date':'2021-08-10'}}}
        require_before_after(result,event,{}, {'b':'/before.png','a':'/after.png'})
        with self.assertRaises(ValueError):require_before_after(result,event,{}, {'b':'/before.png'})
        result['high_resolution']['after']['date']='2021-07-25'
        with self.assertRaises(ValueError):require_before_after(result,event,{}, {'b':'/before.png','a':'/after.png'})
    def test_private_fields_are_removed_without_mutating_source(self):
        value={'nested':[{'value':None,'local_path':'/root/private','access_token':'secret','FIRMS_MAP_KEY':'secret'}]}
        self.assertEqual(sanitize(value),{'nested':[{'value':None}]});self.assertIn('local_path',value['nested'][0])
    def test_unknown_private_annotation_is_rejected(self):
        for value in ['/root/secret','Bearer secret','https://example.org/file?X-Amz-Signature=secret']:
            with self.assertRaises(ValueError):sanitize({'annotation':value})
    def test_lossless_compression_and_deduplication(self):
        value={'observations':[{'value':.123456789,'missing':None}]*5000}
        with tempfile.TemporaryDirectory() as temp:
            bundle=Bundle(Path(temp),100000);url=bundle.json(value);self.assertTrue(url.endswith('.gz'));self.assertEqual(url,bundle.json(value));self.assertEqual(len(bundle.files),1)
            self.assertEqual(value,json.loads(gzip.decompress((Path(temp)/url.removeprefix('/demo/')).read_bytes())))
    def test_budget_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):Bundle(Path(temp),2).json({'value':12345})


class ClonePreparationTests(unittest.TestCase):
    def test_removes_only_deleted_manifest_owned_source_copies(self):
        script = Path(__file__).resolve().parents[3] / 'scripts' / 'prepare_vercel_clone.py'
        spec = importlib.util.spec_from_file_location('afterfire_clone_preparation', script)
        preparation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preparation)
        with tempfile.TemporaryDirectory() as temp:
            preparation.SOURCE = Path(temp) / 'frontend'
            preparation.CLONE = Path(temp) / 'clone'
            (preparation.SOURCE / 'src').mkdir(parents=True)
            (preparation.CLONE / 'src').mkdir(parents=True)
            (preparation.SOURCE / 'src/live.ts').write_text('current')
            for name in ('live.ts', 'obsolete.ts', 'custom.ts'):
                (preparation.CLONE / 'src' / name).write_text('saved')
            manifest = preparation.CLONE / 'clone-source.json'
            manifest.write_text(json.dumps({'source_files': {'src/live.ts': 'hash', 'src/obsolete.ts': 'hash'}}))
            preparation.remove_stale_sources()
            self.assertFalse((preparation.CLONE / 'src/obsolete.ts').exists())
            self.assertTrue((preparation.CLONE / 'src/live.ts').exists())
            self.assertTrue((preparation.CLONE / 'src/custom.ts').exists())
            manifest.write_text(json.dumps({'source_files': {'../outside.ts': 'hash'}}))
            with self.assertRaises(ValueError):
                preparation.remove_stale_sources()


if __name__=='__main__':unittest.main()
