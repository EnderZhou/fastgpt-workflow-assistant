"""Build and verify the single WorkBuddy expert with the released skill embedded unchanged."""
from pathlib import Path
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skill/fastgpt-workflow-assistant'
sys.path.insert(0, str(SKILL / 'scripts'))
from inspect_expert_versions import inspect


def main():
    c = json.loads((ROOT / 'expert/config.json').read_text(encoding='utf-8-sig'))
    version = json.loads((SKILL / 'assets/skill-version.json').read_text(encoding='utf-8-sig'))['version']
    assert c['version'] == version
    assert c['name'] == c['plugin'] == c['agentName'] == 'fastgpt-workflow-expert'
    assert c['expertType'] == 'agent' and 'tools' not in c
    assert c['skills'] == ['./skills/fastgpt-workflow-assistant']
    assert c['defaultInitPrompt'] == c['quickPrompts'][0]
    assert len(c['tags']) == len(c['quickPrompts']) == 3
    for field in ('displayName', 'profession', 'displayDescription', 'defaultInitPrompt'):
        assert all(isinstance(c[field][lang], str) and c[field][lang].strip() for lang in ('zh', 'en'))
    assert all(len(c['displayName'][lang]) <= 15 for lang in ('zh', 'en'))
    assert 40 <= len(c['displayDescription']['zh']) <= 50
    source = ROOT / 'dist' / f'fastgpt-workflow-assistant-v{version}_WorkBuddy_import-ready.zip'
    with zipfile.ZipFile(source) as z:
        assert z.testzip() is None
        original = {name: z.read(name) for name in z.namelist()}
    assert json.loads(original['assets/skill-version.json'])['version'] == version
    skill_prefix = 'skills/fastgpt-workflow-assistant/'
    entries = {skill_prefix + name: data for name, data in original.items()}
    assert all(not name.startswith('/') and '..' not in name.split('/') and '\\' not in name for name in entries)
    avatar = (ROOT / 'expert/avatar.png').read_bytes()
    assert len(avatar) <= 500 * 1024 and struct.unpack('>II', avatar[16:24]) == (512, 512)
    entries[c['avatar']] = avatar
    entries['.codebuddy-plugin/plugin.json'] = (json.dumps(c, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    front = '\n'.join(['---', 'name: ' + c['agentName'], 'description: ' + json.dumps(c['description']),
                       'displayName:', '  zh: ' + json.dumps(c['displayName']['zh'], ensure_ascii=False),
                       '  en: ' + json.dumps(c['displayName']['en']), 'profession:',
                       '  zh: ' + json.dumps(c['profession']['zh'], ensure_ascii=False),
                       '  en: ' + json.dumps(c['profession']['en']), 'maxTurns: 100',
                       'skills: [fastgpt-workflow-assistant]', '---', ''])
    entries['agents/' + c['agentName'] + '.md'] = (front + '\n' + (ROOT / 'expert/agent.md').read_text(encoding='utf-8')).encode('utf-8')
    entries['README.md'] = (ROOT / 'expert/README.md').read_bytes()
    entries['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    # Validate local links in the actual expert ZIP, not only its source tree.
    for name, data in entries.items():
        if name.endswith('.md'):
            import posixpath
            for link in re.findall(r'\]\(([^)]+)\)', data.decode('utf-8-sig')):
                target = link.split('#', 1)[0].strip('<>')
                if not target or re.match(r'[a-zA-Z]+:', target):
                    continue
                assert posixpath.normpath(posixpath.join(posixpath.dirname(name), target)) in entries, (name, target)
    target = ROOT / 'dist' / f'fastgpt-workflow-expert-v{version}_WorkBuddy_expert.zip'
    # Versioned outputs may be regenerated before publication; do not regenerate a published release.
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert {n[len(skill_prefix):]: z.read(n) for n in z.namelist() if n.startswith(skill_prefix)} == original
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        with zipfile.ZipFile(target) as z:
            z.extractall(directory)
        embedded_root = Path(directory) / skill_prefix
        result = subprocess.run([sys.executable, '-X', 'utf8', str(embedded_root / 'scripts/smoke_test_skill.py')],
                                capture_output=True, text=True, encoding='utf-8', env=env, timeout=90)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
    versions = inspect(target)
    assert len(versions['experts']) == len(versions['skills']) == 1
    assert versions['experts'][0]['expert_version'] == versions['skills'][0]['skill_version'] == version
    assert not versions['warnings']
    report = {'expert': c['name'], 'expert_version': version, 'embedded_skill_version': version,
              'file': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest().upper(),
              'files': len(entries), 'embedded_skill_byte_identical': True, 'zip_crc': 'passed',
              'extracted_skill_smoke': 'passed', 'name_length_limit': 15,
              'name_characters': {lang: len(s) for lang, s in c['displayName'].items()},
              'client_import': 'not_verified', 'marketplace_review': 'not_submitted',
              'marketplace_effective_version': 'user reported 1.0.0; embedded skill 2.9.3',
              'version_evidence': versions}
    (ROOT / 'dist' / f'fastgpt-workflow-expert-v{version}_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
