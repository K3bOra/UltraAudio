#!/usr/bin/env python3
"""Generate a self-contained POSIX/Python2+3 installer from the tested updater."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]

def render():
    template = (BASE / 'scripts/updater_template.py').read_text(encoding='utf-8')
    template = template[:template.index("if __name__ == '__main__':")]
    template = template.replace("BUILD_CHANNEL = '__CHANNEL__'", 'BUILD_CHANNEL = None')
    main = (BASE / 'scripts/installer_main.py').read_text(encoding='utf-8')
    # ASCII wrapper: Python 2 reads the coding declaration from the heredoc.
    wrapper = '''#!/bin/sh
# UltraAudio unified installer: platform-specific, verified downloads only.
set -u
UA_PYTHON=''
for ua_candidate in python3 python2.7 python2 python; do
    if command -v "$ua_candidate" >/dev/null 2>&1 &&
       "$ua_candidate" -c 'import sys; v=sys.version_info; sys.exit(0 if ((v[0] == 2 and v >= (2, 7, 9)) or (v[0] == 3 and v >= (3, 5))) else 1)' 2>/dev/null; then
        UA_PYTHON=$ua_candidate
        break
    fi
done
if [ -z "$UA_PYTHON" ]; then
    printf '%s\\n' '[ERROR] No supported Python runtime on this receiver.'
    exit 1
fi
"$UA_PYTHON" - "$@" <<'ULTRAAUDIO_INSTALL_PY'
'''
    footer = '''ULTRAAUDIO_INSTALL_PY
ua_result=$?
case "$0" in /tmp/ultraaudio_install.sh) rm -f -- "$0" ;; esac
exit "$ua_result"
'''
    return wrapper + template + main + '\n' + footer

if __name__ == '__main__':
    (BASE / 'install.sh').write_text(render(), encoding='utf-8')
