"""Deployment boundaries, without modifying localhost state or starting services."""
import unittest
from pathlib import Path
import tempfile
from zipfile import ZipFile
from deploy.render.start import public_port, runtime_environment, validate_password
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
        for value in ('0', '80', '3000', '8000', '11434', '65536', '10000;bad'):
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


if __name__ == '__main__':
    unittest.main()
