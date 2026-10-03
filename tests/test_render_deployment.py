"""Deployment boundaries, without modifying localhost state or starting services."""
import unittest
from pathlib import Path
import tempfile
import io
import json
from unittest.mock import Mock, patch
from zipfile import ZipFile
from deploy.render.start import Services, public_port, runtime_environment, validate_password
from deploy.render.package_extension import package_extension


class RenderConfigurationTests(unittest.TestCase):
    def test_extension_download_contains_installable_source_without_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'
            source.mkdir()
            for name in ('manifest.json', 'background.js', 'options.html', '.env.js', '.env.local'):
                (source/name).write_text('{}')
            archive = root/'extension.zip'
            package_extension(source, archive)
            with ZipFile(archive) as bundle:
                self.assertEqual(set(bundle.namelist()),
                                 {'extension/manifest.json', 'extension/background.js', 'extension/options.html'})

    def test_render_uses_persistent_paths_and_private_listeners(self):
        env = runtime_environment({'CHAI_HOST_PASSWORD': 'do-not-inherit-this',
                                   'RENDER_EXTERNAL_URL': 'https://demo.onrender.com',
                                   'NITRO_PORT': '10000', 'OLLAMA_HOST': '0.0.0.0:11434'})
        self.assertNotIn('CHAI_HOST_PASSWORD', env)
        self.assertEqual(env['DATABASE_URL'].replace('\\', '/'), 'sqlite:////var/data/analytics.sqlite3')
        self.assertEqual(env['CHROMA_PERSIST_DIR'].replace('\\', '/'), '/var/data/chroma')
        self.assertEqual(env['OLLAMA_MODELS'].replace('\\', '/'), '/var/data/ollama')
        self.assertEqual(env['NITRO_HOST'], '127.0.0.1')
        self.assertEqual(env['NITRO_PORT'], '3000')
        self.assertEqual(env['OLLAMA_HOST'], '127.0.0.1:11434')
        self.assertEqual(env['CORS_ORIGINS'], 'https://demo.onrender.com')

    def test_environment_is_not_mutated_and_explicit_database_is_preserved(self):
        original = {'DATABASE_URL': 'postgresql://example', 'CORS_ORIGINS': 'https://custom.test'}
        self.assertEqual(runtime_environment(original)['DATABASE_URL'], original['DATABASE_URL'])
        self.assertEqual(runtime_environment(original)['CORS_ORIGINS'], original['CORS_ORIGINS'])
        self.assertEqual(len(original), 2)

    def test_invalid_ports_passwords_and_external_origins_fail_closed(self):
        for value in ('0', '80', '3000', '8000', '11434', '18012', '18013', '19099', '65536', '10000;bad'):
            with self.assertRaises(ValueError):
                public_port(value)
        self.assertEqual(public_port('10000'), 10000)
        for value in ('', 'short', 'x'*73, 'x'*16+'\n', 'x'*16+'\u00e9'):
            with self.assertRaises(ValueError):
                validate_password(value)
        validate_password('sample-password-123')
        for value in ('http://demo.test', 'https://user:secret@demo.test'):
            with self.assertRaises(ValueError):
                runtime_environment({'RENDER_EXTERNAL_URL': value})

    def test_blank_environment_values_use_persistent_defaults(self):
        env = runtime_environment(dict.fromkeys(('DATABASE_URL', 'OLLAMA_EMBED_MODEL',
                                  'OLLAMA_CHAT_MODEL', 'C_RAM_BUDGET_MB', 'CHAI_MODEL_AUTO_PULL'), '  '))
        self.assertEqual(env['DATABASE_URL'], 'sqlite:////var/data/analytics.sqlite3')
        self.assertEqual(env['OLLAMA_EMBED_MODEL'], 'embeddinggemma')
        self.assertEqual(env['OLLAMA_CHAT_MODEL'], 'llama3.2:3b')
        self.assertEqual(env['C_RAM_BUDGET_MB'], '6144')
        self.assertEqual(env['CHAI_MODEL_AUTO_PULL'], 'true')

    def test_ephemeral_or_escaping_sqlite_paths_are_rejected(self):
        for url in ('sqlite://', 'sqlite:///:memory:', 'sqlite:///data/local.db',
                    'sqlite:////app/data/local.db', 'sqlite:////var/data/../lost.db'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                runtime_environment({'DATABASE_URL': url})
        self.assertEqual(runtime_environment({'DATABASE_URL': 'sqlite:////var/data/custom.db'})['DATABASE_URL'],
                         'sqlite:////var/data/custom.db')
        with self.assertRaises(ValueError):
            runtime_environment({'CHROMA_HOST': 'localhost'})

    def test_invalid_hosted_runtime_values_fail_before_process_start(self):
        for key in ('OLLAMA_NUM_PARALLEL', 'OLLAMA_MAX_LOADED_MODELS', 'OLLAMA_CONTEXT_LENGTH', 'C_RAM_BUDGET_MB'):
            for value in ('0', '-1', 'bad'):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    runtime_environment({key: value})
        with self.assertRaises(ValueError):
            runtime_environment({'CHAI_MODEL_AUTO_PULL': 'flase'})


class ModelBootstrapTests(unittest.TestCase):
    def inventory(self, *names):
        return {'models': [{'name': name, 'digest': 'verified-model-digest'} for name in names]}

    def run_bootstrap(self, responses, env=None, returncodes=None):
        services = Services(runtime_environment(env or {}))
        replies = iter(responses)
        codes = iter(returncodes or [0] * 10)
        def response(*args, **kwargs):
            value = next(replies)  # Unexpected retries fail the test instead of hanging.
            if isinstance(value, Exception):
                raise value
            return io.BytesIO(json.dumps(value).encode())
        def launch(*args, **kwargs):
            process = Mock(returncode=next(codes))
            process.poll.return_value = process.returncode
            return process
        with patch('deploy.render.start.urllib.request.urlopen', side_effect=response), \
             patch.object(services, 'launch', side_effect=launch) as spawned, \
             patch.object(services.stop, 'wait', return_value=False):
            services.bootstrap_models()
        return services, spawned

    def test_first_boot_waits_for_both_committed_model_manifests(self):
        services, spawned = self.run_bootstrap([
            self.inventory(), self.inventory('embeddinggemma:latest'),
            self.inventory('embeddinggemma:latest'),
            self.inventory('embeddinggemma:latest', 'llama3.2:3b')])
        self.assertTrue(services.models_ready.is_set())
        self.assertEqual([call.args[1] for call in spawned.call_args_list],
                         [['ollama', 'pull', 'embeddinggemma'], ['ollama', 'pull', 'llama3.2:3b']])

    def test_failed_pull_transport_and_malformed_inventory_retry(self):
        services, spawned = self.run_bootstrap([
            OSError('transport unavailable'), [], {'models': [None]},
            {'models': [{'name': 'embeddinggemma:latest'}]}, self.inventory(),
            self.inventory(), self.inventory('embeddinggemma:latest', 'llama3.2:3b'),
            self.inventory('embeddinggemma:latest', 'llama3.2:3b')], returncodes=[1, 0])
        self.assertTrue(services.models_ready.is_set())
        self.assertEqual(spawned.call_count, 2)

    def test_successful_cli_without_manifest_does_not_open_api(self):
        services, spawned = self.run_bootstrap([
            self.inventory(), self.inventory(),
            self.inventory('embeddinggemma:latest', 'llama3.2:3b'),
            self.inventory('embeddinggemma:latest', 'llama3.2:3b')])
        self.assertTrue(services.models_ready.is_set())
        self.assertEqual(spawned.call_count, 2)

    def test_existing_namespaced_models_do_not_download_on_restart(self):
        inventory = self.inventory('registry.test:5000/team/embed:latest', 'chat:study')
        services, spawned = self.run_bootstrap([inventory, inventory],
            {'OLLAMA_EMBED_MODEL': 'registry.test:5000/team/embed', 'OLLAMA_CHAT_MODEL': 'chat:study'})
        self.assertTrue(services.models_ready.is_set())
        spawned.assert_not_called()

    def test_manual_setup_waits_without_launching_downloads(self):
        services, spawned = self.run_bootstrap([
            self.inventory(), self.inventory('embeddinggemma:latest', 'llama3.2:3b'),
            self.inventory('embeddinggemma:latest', 'llama3.2:3b')], {'CHAI_MODEL_AUTO_PULL': 'false'})
        self.assertTrue(services.models_ready.is_set())
        spawned.assert_not_called()

    def test_shutdown_during_download_never_opens_api(self):
        services = Services(runtime_environment({}))
        process = Mock(returncode=None)
        process.poll.return_value = None
        def stop(*args):
            services.stop.set()
            return True
        with patch('deploy.render.start.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(self.inventory()).encode())), \
             patch.object(services, 'launch', return_value=process), patch.object(services.stop, 'wait', side_effect=stop):
            services.bootstrap_models()
        self.assertFalse(services.models_ready.is_set())


if __name__ == '__main__':
    unittest.main()
