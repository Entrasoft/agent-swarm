import contextlib
import io
import getpass
import warnings
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from swarm_lab.credentials import configure_key, get_api_key, check_model, main


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.old=Path.cwd()
        os.chdir(self.path)
        self.addCleanup(os.chdir,self.old)
        self.env=patch.dict(os.environ,{},clear=True)
        self.env.start();self.addCleanup(self.env.stop)
        self.key='unit-test-placeholder-value'

    def write_key(self, key=None, permissions=0o600):
        file=self.path/'.env'
        file.write_text('OPENAI_API_KEY='+(key or self.key)+'\n')
        file.chmod(permissions)
        return file

    def test_environment_precedes_file_and_status_never_prints_key(self):
        self.write_key()
        with patch.dict(os.environ,{'OPENAI_API_KEY':'environment-test-placeholder'}):
            self.assertEqual(get_api_key(),'environment-test-placeholder')
            output=io.StringIO()
            with contextlib.redirect_stdout(output): main(['status'])
        self.assertNotIn('placeholder',output.getvalue())
        self.assertIn('environment',output.getvalue())

    def test_protected_file_parsed_without_shell_evaluation(self):
        self.write_key()
        self.assertEqual(get_api_key(),self.key)
        self.write_key('literal-$(do-not-execute)')
        self.assertEqual(get_api_key(),'literal-$(do-not-execute)')

    @unittest.skipUnless(os.name=='posix','POSIX permissions')
    def test_permissive_file_and_symlink_rejected(self):
        file=self.write_key(permissions=0o644)
        with self.assertRaisesRegex(ValueError,'permissions 600'):get_api_key()
        file.rename(self.path/'elsewhere')
        file.symlink_to(self.path/'elsewhere')
        with self.assertRaises(ValueError):get_api_key()

    def test_missing_ambiguous_and_invalid_keys_have_redacted_errors(self):
        with self.assertRaises(ValueError):get_api_key()
        file=self.write_key()
        file.write_text('OPENAI_API_KEY=first-placeholder\nOPENAI_API_KEY=second-placeholder\n')
        with self.assertRaisesRegex(ValueError,'exactly once'):get_api_key()
        self.write_key('invalid private value')
        with self.assertRaises(ValueError) as exc:get_api_key()
        self.assertNotIn('private value',str(exc.exception))

    def test_setup_hidden_prompt_ignored_permissioned_and_nonclobbering(self):
        with patch('subprocess.run') as command, patch('sys.stdin.isatty',return_value=True), \
             patch('getpass.getpass',return_value=self.key):
            command.return_value.returncode=0
            file=configure_key()
            self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
            self.assertEqual(get_api_key(),self.key)
            with self.assertRaisesRegex(ValueError,'already exists'):configure_key()
        self.assertEqual(list(self.path.glob('.env.setup-*')),[])

    def test_setup_refuses_unignored_location_or_visible_fallback(self):
        with patch('subprocess.run') as command:
            command.return_value.returncode=1
            with self.assertRaisesRegex(ValueError,'ignored'):configure_key()
        with patch('subprocess.run') as command, patch('sys.stdin.isatty',return_value=False):
            command.return_value.returncode=0
            with self.assertRaisesRegex(ValueError,'interactive'):configure_key()
        self.assertFalse((self.path/'.env').exists())

    def test_metadata_check_sends_only_get_and_never_returns_key(self):
        self.write_key()
        response=io.BytesIO(json.dumps({'id':'gpt-5.6-terra'}).encode())
        with patch('urllib.request.urlopen',return_value=response) as call:
            result=check_model()
        request=call.call_args.args[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertIsNone(request.data)
        self.assertEqual(result['generation_requests'],0)
        self.assertNotIn(self.key,json.dumps(result))

    def test_http_error_body_and_key_are_not_disclosed(self):
        self.write_key()
        error=urllib.error.HTTPError('https://api.openai.com/v1/models/gpt-5.6-terra',403,
            'sensitive-body-'+self.key,{},io.BytesIO(self.key.encode()))
        with patch('urllib.request.urlopen',side_effect=error):
            with self.assertRaises(ValueError) as exc:check_model()
        self.assertNotIn(self.key,str(exc.exception))
        self.assertIn('permissions',str(exc.exception))


    def test_hidden_input_warning_fails_before_writing(self):
        def unsafe_fallback(*args, **kwargs):
            warnings.warn('echo control failed', getpass.GetPassWarning)
            return self.key
        with patch('subprocess.run') as command, patch('sys.stdin.isatty',return_value=True), \
             patch('getpass.getpass',side_effect=unsafe_fallback):
            command.return_value.returncode=0
            with self.assertRaisesRegex(ValueError,'Hidden input'):
                configure_key()
        self.assertFalse((self.path/'.env').exists())

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO')
    def test_fifo_key_file_is_rejected_without_waiting_for_a_writer(self):
        os.mkfifo(self.path/'.env', 0o600)
        with self.assertRaisesRegex(ValueError,'regular file'):
            get_api_key()
