"""Recording defaults and microphone routing boundaries."""
import configparser
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(ROOT / 'bin' / name))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


audio = load('mintbook-audio')
record = load('mintbook-record')
installer = load('recording-install')


class RecordingTests(unittest.TestCase):
    def test_profile_retains_customizations_on_rerun(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            record.setup(home, (2304, 1440))
            profile = home / '.config/obs-studio/basic/profiles/Mintbook_Recording/basic.ini'
            scenes = home / '.config/obs-studio/basic/scenes/Mintbook_Recording.json'
            profile.write_text('[General]\nName=My customized setup\n')
            scenes.write_text('{"custom": true}')
            record.setup(home, (1920, 1080))
            self.assertIn('My customized setup', profile.read_text())
            self.assertEqual(json.loads(scenes.read_text()), {'custom': True})

    def test_recording_has_mix_and_isolated_audio_without_streaming(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            record.setup(home, (2304, 1440))
            config = configparser.ConfigParser(interpolation=None)
            config.read(home / '.config/obs-studio/basic/profiles/Mintbook_Recording/basic.ini')
            self.assertIn('RecTracks=7', (home / '.config/obs-studio/basic/profiles/Mintbook_Recording/basic.ini').read_text())
            self.assertEqual(config['SimpleOutput']['RecTracks'], '7')
            self.assertEqual(config['SimpleOutput']['RecFormat2'], 'mkv')
            self.assertEqual(config['Video']['OutputCX'], '1280')
            self.assertEqual(config['Video']['OutputCY'], '800')
            self.assertEqual(config['Video']['AutoRemux'], 'true')
            self.assertEqual(config['Video']['FPSInt'], '24')
            start = json.loads(config['Hotkeys']['OBSBasic.StartRecording'])['bindings'][0]['key']
            stop = json.loads(config['Hotkeys']['OBSBasic.StopRecording'])['bindings'][0]['key']
            self.assertNotEqual(start, stop)
            scenes = json.loads((home / '.config/obs-studio/basic/scenes/Mintbook_Recording.json').read_text())
            self.assertEqual(scenes['AuxAudioDevice1']['mixers'], 3)
            self.assertEqual(scenes['DesktopAudioDevice1']['mixers'], 5)
            self.assertEqual(scenes['sources'][0]['id'], 'xshm_input')
            self.assertFalse((home / '.config/obs-studio/basic/profiles/Mintbook_Recording/service.json').exists())

    def test_verified_local_driver_selects_hardware_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            driver = home / '.local/share/mintbook/recording/vaapi/i965_drv_video.so'
            driver.parent.mkdir(parents=True)
            driver.touch()
            record.setup(home, (1920, 1080))
            profile = home / '.config/obs-studio/basic/profiles/Mintbook_Recording'
            config = configparser.ConfigParser(interpolation=None)
            config.read(profile / 'basic.ini')
            self.assertEqual(config['Output']['Mode'], 'Advanced')
            self.assertEqual(config['AdvOut']['RecEncoder'], 'ffmpeg_vaapi')
            self.assertEqual(config['AdvOut']['RecTracks'], '7')
            settings = json.loads((profile / 'recordEncoder.json').read_text())
            self.assertEqual(settings['rate_control'], 'CQP')
            self.assertEqual(settings['ffmpeg_opts'], 'quality=7')
            self.assertEqual(record.hardware_driver(home), driver.parent)

    def test_minimized_recorder_is_raised_without_starting_another_instance(self):
        from types import SimpleNamespace
        replies = [SimpleNamespace(stdout='100 200', returncode=0),
                   SimpleNamespace(stdout='Qt helper', returncode=0),
                   SimpleNamespace(stdout='OBS 30 - Profile: Mintbook Recording', returncode=0),
                   SimpleNamespace(returncode=0)]
        with patch.object(record.shutil, 'which', return_value='/usr/bin/xdotool'), \
                patch.object(record.subprocess, 'run', side_effect=replies) as run:
            self.assertTrue(record.raise_existing())
        self.assertNotIn('--onlyvisible', run.call_args_list[0].args[0])
        self.assertEqual(run.call_args.args[0], ['xdotool', 'windowactivate', '--sync', '200'])

    def test_install_rerun_extends_undo_and_retains_original_backup(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            state = home / '.config/mintbook/recording-install.json'
            original = home / '.local/bin/mintbook-record'
            original.parent.mkdir(parents=True)
            original.write_text('original launcher')
            with patch.object(installer, 'HOME', home), patch.object(installer, 'STATE', state), \
                    patch.object(installer.shutil, 'which', return_value='/usr/bin/test'), \
                    patch.object(installer, 'run', return_value=SimpleNamespace(stdout='previous shortcut')):
                installer.install()
                original.write_text('changed after install')
                added = home / '.local/bin/added-helper'
                base_targets = installer.targets()
                with patch.object(installer, 'targets', return_value=base_targets + [(ROOT / 'bin/mintbook-record', added)]):
                    installer.install()
                self.assertIn(str(added), {e['path'] for e in json.loads(state.read_text())['files']})
                installer.revert()
            self.assertEqual(original.read_text(), 'original launcher')
            self.assertFalse(added.exists())
            self.assertFalse(state.exists())

    def test_input_menu_supplies_structured_options(self):
        import contextlib
        import io
        sources = [{'name': 'mic', 'description': 'Built-in microphone'}]
        out = io.StringIO()
        with patch.object(audio, 'microphones', return_value=sources), \
                patch.object(audio, 'pactl', return_value='mic'), contextlib.redirect_stdout(out):
            audio.tile('input')
        self.assertEqual(json.loads(out.getvalue())['options'], [['mic', 'Built-in microphone']])
        self.assertEqual(audio.microphone_label({'active_port': 'analog-input-internal-mic'}), 'Built-in microphone')

    def test_monitors_do_not_appear_as_microphones(self):
        sources = [{'name': 'mic', 'monitor_of_sink': None},
                   {'name': 'output.monitor', 'monitor_of_sink': 37}]
        with patch.object(audio, 'pactl', return_value=json.dumps(sources)):
            self.assertEqual([s['name'] for s in audio.microphones()], ['mic'])

    def test_switching_mic_never_moves_desktop_audio_or_dsp_links(self):
        streams = [{'index': 1, 'source': 10, 'client': 5},
                   {'index': 2, 'source': 37, 'client': 6},
                   {'index': 3, 'source': 10, 'client': None}]
        def reply(*args):
            return json.dumps(streams) if args == ('-f', 'json', 'list', 'source-outputs') else ''
        with patch.object(audio, 'microphones', return_value=[{'name': 'mic', 'index': 10}]), \
                patch.object(audio, 'pactl', side_effect=reply) as call:
            audio.choose('mic')
        moves = [c.args for c in call.call_args_list if c.args[0] == 'move-source-output']
        self.assertEqual(moves, [('move-source-output', '1', 'mic')])

    def test_disconnected_mic_cannot_replace_default(self):
        with patch.object(audio, 'microphones', return_value=[]), patch.object(audio, 'pactl') as call:
            with self.assertRaises(ValueError):
                audio.choose('disconnected')
        call.assert_not_called()

    def test_input_volume_preserves_mute_and_rejects_out_of_range(self):
        with patch.object(audio, 'selected', return_value={'name': 'mic'}), patch.object(audio, 'pactl') as call:
            audio.tile('gain', 'set', '67')
            call.assert_called_once_with('set-source-volume', 'mic', '67%')
            call.reset_mock()
            for value in ('-1', '101', 'nan', 'inf'):
                with self.assertRaises(ValueError):
                    audio.tile('gain', 'set', value)
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
