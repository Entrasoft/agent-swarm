"""Local key setup and a read-only model-access check. Never print credentials."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

KEY_NAME = 'OPENAI_API_KEY'
DEFAULT_FILE = '.env'
MAX_FILE_BYTES = 65536


def _validate_key(value: str) -> str:
    value = value.strip()
    if not 16 <= len(value) <= 2048 or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('The key must be one nonempty line of printable characters, without spaces.')
    return value


def _read_key_file(path: Path) -> str:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    except FileNotFoundError:
        raise ValueError('No API key configured. Run: python3 -m swarm_lab.credentials setup') from None
    except OSError:
        raise ValueError('Cannot safely open the local key file.') from None
    with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('The local key file must be a regular file.')
        if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('The local key file must belong to you and have permissions 600 (chmod 600 .env).')
        if info.st_size > MAX_FILE_BYTES:
            raise ValueError('The local key file is too large.')
        try:
            content = stream.read(MAX_FILE_BYTES + 1)
        except UnicodeError:
            raise ValueError('The local key file must be UTF-8 text.') from None
    values = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        name, value = stripped.split('=', 1)
        if name.strip() == KEY_NAME:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values.append(value)
    if len(values) != 1:
        raise ValueError('The local key file must define OPENAI_API_KEY exactly once.')
    return _validate_key(values[0])


def get_api_key() -> str:
    """Environment first, then a protected .env in the current working directory.

    The file is parsed as data. No shell expansion, arbitrary environment loading,
    or credential value is included in logs, errors, configuration or events.
    """
    value = os.environ.get(KEY_NAME)
    if value:
        return _validate_key(value)
    return _read_key_file(Path.cwd() / DEFAULT_FILE)


def configure_key(replace: bool = False) -> Path:
    """Prompt on a real terminal and write an ignored file with owner-only access."""
    path = Path.cwd() / DEFAULT_FILE
    try:
        ignored = subprocess.run(['git', 'check-ignore', '-q', '--', DEFAULT_FILE],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        ignored = False
    if not ignored:
        raise ValueError('Run setup inside the agent-swarm checkout, where .env is ignored by Git.')
    if path.is_symlink():
        raise ValueError('Refusing to replace a symbolic link at .env.')
    if path.exists() and not replace:
        raise ValueError('.env already exists. Use setup --replace only if you intend to replace that file.')
    if not sys.stdin.isatty():
        raise ValueError('Run setup in an interactive Terminal; do not pipe a key into this command.')
    # getpass can otherwise fall back to visible input when terminal echo control fails.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            value = _validate_key(getpass.getpass('OpenAI API key (hidden input): '))
        except getpass.GetPassWarning:
            raise ValueError('Hidden input is unavailable. Use an interactive Terminal.') from None
    descriptor, temporary = tempfile.mkstemp(prefix='.env.setup-', dir=Path.cwd())
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write('# Local secret; never commit this file.\nOPENAI_API_KEY=' + value + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # Link atomically with no clobber if a file appeared during the prompt.
            os.link(temporary, path)
            os.unlink(temporary)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def check_model(model: str = 'gpt-5.6-terra') -> dict:
    """GET model metadata only: no generation request or inference spend."""
    key = get_api_key()
    url = 'https://api.openai.com/v1/models/' + urllib.parse.quote(model, safe='')
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key}, method='GET')
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        messages = {
            401: 'The API rejected the key. Check whether it is active and copied correctly.',
            403: 'Model metadata access was denied. Check key/project permissions; inference access is not established.',
            404: 'This model is unavailable to this key, or the model ID was not found.',
            429: 'The API rate-limited this check. Retry later and inspect account/project limits.'}
        raise ValueError(messages.get(exc.code, f'Model metadata check failed with HTTP {exc.code}.')) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('Could not reach the model metadata endpoint. No generation was requested.') from None
    except (ValueError, TypeError):
        raise ValueError('The model metadata response was not valid JSON.') from None
    if not isinstance(body, dict) or body.get('id') != model:
        raise ValueError('The metadata response did not identify the requested model.')
    return {'model': model, 'metadata_access': 'available', 'generation_requests': 0,
            'note': 'This checks model visibility, not Responses write permission or your credit balance.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('setup', help='Save a key using a hidden local prompt')
    setup.add_argument('--replace', action='store_true', help='Replace an existing local .env file')
    commands.add_parser('status', help='Report key availability without showing its value')
    check = commands.add_parser('check', help='Check model metadata access without generating output')
    check.add_argument('--model', default='gpt-5.6-terra')
    args = parser.parse_args(argv)
    try:
        if args.command == 'setup':
            configure_key(args.replace)
            print('Saved .env with owner-only permissions. The key was not printed. No API request was made.')
            if os.environ.get(KEY_NAME):
                print('Note: an existing OPENAI_API_KEY environment variable takes precedence over .env.')
        elif args.command == 'status':
            get_api_key()
            print('Key configured (environment).' if os.environ.get(KEY_NAME) else 'Key configured (protected local .env).')
        else:
            print(json.dumps(check_model(args.model), indent=2))
    except (ValueError, OSError, EOFError) as exc:
        # IO errors have no key values; do not expose arbitrary network response bodies.
        parser.exit(2, f'Error: {exc}\n')
    except KeyboardInterrupt:
        parser.exit(130, 'Setup cancelled.\n')


if __name__ == '__main__':
    main()
