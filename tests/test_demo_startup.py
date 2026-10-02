"""Failure-path regressions for demo startup and exact Ollama model readiness."""
import io
import json
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import start_local as launcher
from ml.llm_service import LLMService
from ml.rag_engine import OllamaEmbeddings


class ModelReadinessTests(unittest.TestCase):
    def status(self, requested, installed):
        payload = json.dumps({'models': [{'name': name} for name in installed]}).encode()
        chat, embed = LLMService(), OllamaEmbeddings()
        chat.model = embed.model = requested
        with patch('urllib.request.urlopen', side_effect=lambda *args, **kwargs: io.BytesIO(payload)):
            return chat.status()['model_ready'], embed.health()['embedding_model_ready']

    def test_implicit_latest_does_not_match_other_tag(self):
        self.assertEqual(self.status('demo', ['demo:3b']), (False, False))

    def test_implicit_and_explicit_latest_match(self):
        self.assertEqual(self.status('demo', ['demo:latest']), (True, True))
        self.assertEqual(self.status('demo:latest', ['demo']), (True, True))

    def test_explicit_tag_matches_only_same_tag(self):
        self.assertEqual(self.status('demo:3b', ['demo:latest']), (False, False))
        self.assertEqual(self.status('demo:3b', ['demo:3b']), (True, True))

    def test_registry_port_does_not_replace_latest_tag(self):
        self.assertEqual(self.status('localhost:5000/demo', ['localhost:5000/demo:3b']), (False, False))
        self.assertEqual(self.status('localhost:5000/demo', ['localhost:5000/demo:latest']), (True, True))

    def test_unreachable_server_is_not_ready(self):
        with patch('urllib.request.urlopen', side_effect=OSError('offline')):
            self.assertFalse(LLMService().status()['model_ready'])
            self.assertFalse(OllamaEmbeddings().health()['embedding_model_ready'])


class LauncherTests(unittest.TestCase):
    def test_node_version_rejects_previous_documented_18_and_20(self):
        for version in ('v18.20.0', 'v20.19.0', 'v22.11.0', 'invalid'):
            self.assertFalse(launcher.node_supported(version), version)
        for version in ('v22.12.0', 'v22.23.0', 'v24.0.0'):
            self.assertTrue(launcher.node_supported(version), version)

    def test_preflight_does_not_accept_wrong_installed_tag(self):
        tags = {'models': [{'name':'embeddinggemma:300m'}, {'name':'llama3.2:3b'}]}
        self.assertEqual(launcher.missing_models(tags, {}), ['embeddinggemma'])

    def test_invalid_model_list_reports_configuration_error(self):
        with self.assertRaises(launcher.StartupError):
            launcher.missing_models({'wrong':[]}, {})

    def test_environment_file_preserves_process_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.env').write_text('# Comment\nOLLAMA_CHAT_MODEL="file-model"\nDEMO_TEST_KEY=from-file\n',encoding='utf-8')
            with patch.dict(os.environ, {'OLLAMA_CHAT_MODEL':'process-model'}):
                env=launcher.environment(root)
            self.assertEqual(env['OLLAMA_CHAT_MODEL'],'process-model')
            self.assertEqual(env['DEMO_TEST_KEY'],'from-file')

    def test_real_occupied_port_is_detected(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1',0))
            server.listen()
            self.assertFalse(launcher.port_available(server.getsockname()[1]))

    def test_installer_failure_is_fatal(self):
        with patch('subprocess.run',return_value=Mock(returncode=1)):
            with self.assertRaises(launcher.StartupError):
                launcher.checked_run(['install'],launcher.ROOT,{})

    def test_early_service_exit_never_reports_ready(self):
        process=Mock()
        process.poll.return_value=1
        with self.assertRaisesRegex(launcher.StartupError,'exited early'):
            launcher.wait_ready(process,lambda:True,'Frontend')

    def test_dependency_installer_uses_current_interpreter_and_lockfile(self):
        with patch('shutil.which',side_effect=lambda name:name), \
             patch('subprocess.check_output',return_value='v22.12.0'), \
             patch('importlib.util.find_spec',return_value=None), \
             patch.object(launcher,'checked_run') as run:
            launcher.ensure_dependencies({}, install=True)
        self.assertEqual(run.call_args_list[0].args[0][:3],[launcher.sys.executable,'-m','pip'])
        self.assertEqual(run.call_args_list[1].args[0],['npm','ci'])

    def test_port_conflict_stops_before_models_or_services(self):
        with patch.object(launcher,'ensure_dependencies',return_value=('node',Path('vite'))), \
             patch.object(launcher,'port_available',return_value=False), \
             patch.object(launcher,'get_json') as get, \
             patch('subprocess.Popen') as popen, patch('sys.stderr',io.StringIO()):
            self.assertEqual(launcher.main(['--no-browser']),1)
        get.assert_not_called()
        popen.assert_not_called()

    def test_existing_ollama_missing_model_never_launches_backend(self):
        with patch.object(launcher,'ensure_dependencies',return_value=('node',Path('vite'))), \
             patch.object(launcher,'port_available',return_value=True), \
             patch.object(launcher,'get_json',return_value={'models':[]}), \
             patch('subprocess.Popen') as popen, patch('sys.stderr',io.StringIO()):
            self.assertEqual(launcher.main(['--no-browser']),1)
        popen.assert_not_called()

    def test_preflight_offline_never_installs_or_starts_processes(self):
        with patch('shutil.which',return_value='node'), \
             patch('subprocess.check_output',return_value='v22.12.0'), \
             patch('importlib.util.find_spec',return_value=Mock()), \
             patch.object(launcher,'port_available',return_value=True), \
             patch.object(launcher,'get_json',side_effect=OSError('offline')), \
             patch.object(launcher,'ensure_dependencies') as install, \
             patch('subprocess.Popen') as popen, patch('sys.stderr',io.StringIO()):
            self.assertEqual(launcher.main(['--check']),1)
        install.assert_not_called()
        popen.assert_not_called()


if __name__=='__main__':
    unittest.main()
