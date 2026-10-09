"""Meaningful cache changes, grouping, and preservation on backend failure."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
def load():
    loader = importlib.machinery.SourceFileLoader('check', str(ROOT/'bin/updates-check'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    return module
check = load()

def row(name, ref, parent='', scope='user', size=10):
    return {'name':name, 'source':name, 'type':'flatpak', 'size':size,
            'flatpak':{'scope':scope, 'ref':ref, 'app':ref.startswith('app/')}, '_parent_ref':parent}

class Cache(unittest.TestCase):
    def test_related_extensions_count_once_and_keep_all_refs(self):
        parent = row('App','app/org.test.App/x86_64/stable')
        child = row('Locale','runtime/org.test.App.Locale/x86_64/stable',parent['flatpak']['ref'])
        result = check.group_flatpaks([parent,child])
        self.assertEqual(len(result),1); self.assertEqual(result[0]['size'],20)
        self.assertEqual(set(result[0]['flatpak']['refs']), {parent['flatpak']['ref'],child['flatpak']['ref']})

    def test_grouping_never_crosses_installation_scopes(self):
        parent = row('App','app/org.test.App/x86_64/stable',scope='system')
        child = row('Locale','runtime/org.test.App.Locale/x86_64/stable',parent['flatpak']['ref'])
        self.assertEqual(len(check.group_flatpaks([parent,child])),2)

    def test_unrelated_dconf_write_does_not_recheck_backends(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'updates.inputs').write_text('same')
            with patch.object(check,'CACHE',tmp), patch.object(check,'input_signature',return_value='same'), \
                 patch.object(check,'collect') as collect, patch.object(check,'flatpaks') as flatpaks:
                self.assertEqual(check.check(['--if-changed']),0)
                collect.assert_not_called(); flatpaks.assert_not_called()

    def test_failed_apt_check_preserves_previous_rows_and_reports_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            listing=Path(tmp,'updates.json'); state=Path(tmp,'updates.state')
            old={'name':'Security fix','source':'pkg','type':'security','size':10}
            listing.write_text(json.dumps({'updates':[old]}))
            with patch.multiple(check,CACHE=tmp,LIST=str(listing),STATE=str(state)), \
                 patch.object(check,'input_signature',return_value='signature'), \
                 patch.object(check,'collect',side_effect=RuntimeError('cache unavailable')), \
                 patch.object(check,'flatpak_enabled',return_value=True), patch.object(check,'online',return_value=False), patch('builtins.print'):
                self.assertEqual(check.check([]),1)
            data=json.loads(listing.read_text())
            self.assertEqual(data['updates'],[old]); self.assertIn('cache unavailable',data['error'])
            self.assertIn('count = 1',state.read_text())

    def test_system_flatpaks_use_mint_group_versions_and_sub_refs(self):
        data=[{'name':'App','real_source_name':'org.test.App','old_version':'1','new_version':'2','size':30,
               'origin':'Flathub','summary':'App update','flatpak_type':'app','ref':'app/org.test.App/x86_64/stable',
               'sub_updates':[{'ref':'runtime/org.test.App.Locale/x86_64/stable','sub_updates':[]}]}]
        from types import SimpleNamespace
        with patch.object(check.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps(data))):
            result=check.mint_system_flatpaks()
        self.assertEqual(len(result),1); self.assertEqual(result[0]['new'],'2')
        self.assertEqual(len(result[0]['flatpak']['refs']),2)

    def test_disabling_flatpaks_clears_cached_rows_even_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            listing=Path(tmp,'updates.json'); state=Path(tmp,'updates.state')
            listing.write_text(json.dumps({'updates':[row('App','app/org.test.App/x86_64/stable')], 'flatpak_checked':1}))
            with patch.multiple(check,CACHE=tmp,LIST=str(listing),STATE=str(state)), \
                 patch.object(check,'input_signature',return_value='signature'), \
                 patch.object(check,'collect',return_value=[]), patch.object(check,'flatpak_enabled',return_value=False), \
                 patch.object(check,'online',return_value=False), patch('builtins.print'):
                self.assertEqual(check.check([]),0)
            self.assertEqual(json.loads(listing.read_text())['updates'],[])
