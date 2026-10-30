#!/usr/bin/env python3
"""Scan staged blobs (default), or all tracked blobs with --all; never print values."""
import re
import subprocess
import sys

ASSIGNMENT = re.compile(rb"(?im)^[ \t]*(?:export[ \t]+)?[\"']?([A-Z][A-Z0-9_]*(?:KEY|TOKEN|PASSWORD|SECRET|USERNAME))[\"']?[ \t]*[:=][ \t]*[\"']?([^\s\"'#;,}]+)")
TOKEN = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")


def findings(path, data):
    result = []
    if TOKEN.search(data):
        result.append('credential or private key')
    for match in ASSIGNMENT.finditer(data):
        value = match[2].lower()
        if value in (b'none', b'null', b'false', b'true', b'removed_firms_key'):
            continue
        if value.startswith((b'$', b'process.', b'os.', b'settings.', b'your_', b'example', b'placeholder', b'<')):
            continue
        # Templates may only carry empty or explicit placeholder credentials.
        if path.endswith('.env.example') or (b'firms' in match[1].lower() and len(value) >= 16):
            result.append(match[1].decode() + ' has a literal value')
    return result


def main():
    args = ['git', 'ls-files', '-z'] if '--all' in sys.argv else ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z']
    failed = False
    for raw in subprocess.check_output(args).split(b'\0'):
        if not raw:
            continue
        path = raw.decode()
        if re.search(r'(^|/)\.env(?:\..+)?$', path) and not path.endswith('.env.example'):
            print(path + ': private environment file is tracked'); failed = True
        data = subprocess.check_output(['git', 'show', ':' + path])
        for reason in findings(path, data):
            print(path + ': ' + reason); failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
