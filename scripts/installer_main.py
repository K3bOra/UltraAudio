
def _installed_parallel_dreamos():
    """Distinguish future parallel 1.0.23/24 from the old DreamOS numbering."""
    import errno
    path = '/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/__init__.py'
    try:
        with open(path, 'rb') as handle:
            source = handle.read(16385)
    except EnvironmentError as error:
        if error.errno == errno.ENOENT:
            return False
        raise
    if len(source) > 16384:
        raise ValueError('Installed version metadata is unexpectedly large')
    import ast
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION_SCHEME' for t in node.targets):
            if ast.literal_eval(node.value) != 'parallel-v1':
                raise ValueError('Unrecognized installed numbering scheme')
            return True
    return False


def _dreamos_numbering_transition(channel, installed, target):
    # Exact, one-time rebase only. New online updates keep normal version order.
    return (channel == 'dreamos' and target in ('1.0.13-dreamos', '1.0.14-dreamos', '1.0.15-dreamos', '1.0.16-dreamos')
            and installed in ('1.0.23-dreamos', '1.0.24-dreamos')
            and not _installed_parallel_dreamos())


def _receiver_python_major():
    try:
        pids = subprocess.check_output(['pidof', 'enigma2']).decode('ascii').split()
        for pid in pids:
            if not pid.isdigit():
                continue
            with open('/proc/%s/maps' % pid, 'rb') as handle:
                found = re.search(br'libpython([23])\.', handle.read())
            if found:
                return int(found.group(1))
    except (EnvironmentError, subprocess.CalledProcessError):
        pass
    return sys.version_info[0]


def installer_main(argv):
    global _VERIFY_CHANNEL
    verify = '--verify-only' in argv
    options = [arg for arg in argv if arg.startswith('--platform=')]
    if (len(options) > 1 or any(arg != '--verify-only' and arg not in options for arg in argv)
            or (options and not verify) or argv.count('--verify-only') > 1):
        raise ValueError('Supported options: --verify-only [--platform=ipk|dreamos]')
    if options:
        _VERIFY_CHANNEL = options[0].split('=', 1)[1]
        if _VERIFY_CHANNEL not in ('ipk', 'dreamos'):
            raise ValueError('Unknown verification platform')
    channel = _channel()
    if sys.version_info < (2, 7) or (sys.version_info[0] == 3 and sys.version_info < (3, 5)):
        raise RuntimeError('Python 2.7.9+ (DreamOS) or Python 3.5+ is required')
    if channel == 'ipk' and _receiver_python_major() < 3:
        raise RuntimeError('The IPK requires a Python 3 Enigma2 image; no package was installed')
    print('\nUltra Audio Final V1 - Ahmed L-HadarY')
    print('[PLATFORM] ' + ('DreamOS / DEB' if channel == 'dreamos' else 'Enigma2 / IPK'))
    filename = 'update-dreamos.json' if channel == 'dreamos' else 'update-ipk.json'
    print('[1/4] Reading verified platform metadata...')
    url = 'https://github.com/%s/releases/latest/download/%s' % (DEFAULT_REPO, filename)
    meta = _verify_meta(DEFAULT_REPO, json.loads(_read_https(url, _MAX_MANIFEST).decode('utf-8')))
    print('[2/4] Downloading and verifying ' + meta['format'].upper() + '...')
    reported = [0.0]

    def progress(size):
        now = _monotonic()
        if now - reported[0] >= 2 or size == meta['size']:
            print('[DOWNLOAD] %d%%' % min(100, 100 * size // meta['size']))
            sys.stdout.flush()
            reported[0] = now
    payload = _read_https(meta['url'], _MAX_PACKAGE, progress)
    if len(payload) != meta['size'] or hashlib.sha256(payload).hexdigest() != meta['sha256']:
        raise ValueError('Package size or SHA256 verification failed')
    control = _ipk_control(payload)
    for key, value in [('Package', PACKAGE_NAME), ('Version', meta['version']), ('Architecture', 'all')]:
        found = re.search(r'^' + key + r':\s*(\S+)', control, re.M)
        if not found or found.group(1) != value:
            raise ValueError('Unexpected package ' + key)
    print('[VERIFIED] ' + meta['version'])
    if verify:
        print('[OK] Verification only; no installation performed.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Run this installer as root on the receiver')
    if not _command_available('enigma2'):
        raise RuntimeError('Enigma2 receiver required; no package was installed')
    command = ['dpkg', '-s', PACKAGE_NAME] if channel == 'dreamos' else ['opkg', 'status', PACKAGE_NAME]
    try:
        status = subprocess.check_output(command, stderr=subprocess.STDOUT).decode('utf-8', 'replace')
    except subprocess.CalledProcessError:
        status = ''
    found = re.search(r'^Version:\s*(\S+)', status, re.M)
    installed = found.group(1) if found else ''
    rebase = _dreamos_numbering_transition(channel, installed, meta['version'])
    if installed and not rebase and not _legacy_transition(installed, meta['version']):
        if _version_tuple(installed) == (0, 0, 0) or _version_revision(installed) > _version_revision(meta['version']):
            raise ValueError('Newer or unrecognized installed version; downgrade refused')
    if installed == meta['version'] and re.search(r'^Status:.* installed\s*$', status, re.M):
        print('[OK] This version is already installed.')
        return
    print('[3/4] Refreshing image package lists...')
    refresh = ['apt-get', 'update'] if channel == 'dreamos' else ['opkg', 'update']
    if not _command_available(refresh[0]):
        raise RuntimeError('Required image package manager is missing: ' + refresh[0])
    if subprocess.call(refresh):
        print('[WARN] Some image feeds did not refresh; using available lists.')
    fd, path = tempfile.mkstemp(prefix='ultraaudio_verified_', suffix='.' + meta['format'], dir='/tmp')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(payload)
        args = ['dpkg', '--force-downgrade' if rebase else '--refuse-downgrade', '-i', path] if channel == 'dreamos' else ['opkg', 'install', path]
        if rebase:
            print('[MIGRATION] Moving legacy DreamOS numbering to parallel version ' + meta['version'] + '.')
        if channel == 'ipk' and _legacy_transition(installed, meta['version']):
            args.insert(2, '--force-downgrade')
        env = dict(os.environ, ULTRAAUDIO_ONLINE_UPDATE='1', ULTRAAUDIO_FEED_UPDATED='1', DEBIAN_FRONTEND='noninteractive')
        print('[4/4] Installing ' + meta['format'].upper() + ' and checking components...')
        if subprocess.call(args, env=env):
            raise RuntimeError('Package installation failed; review package manager output above')
        stat = os.stat(path)
        signature = '%d:%d:%d:%d' % (stat.st_dev, stat.st_ino, stat.st_size, int(stat.st_mtime))
        finish = '/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio/finish_install.sh'
        finish_env = dict(env)
        finish_env.pop('ULTRAAUDIO_ONLINE_UPDATE', None)
        if subprocess.call(['/bin/sh', finish, path, signature], env=finish_env):
            raise RuntimeError('Component checks failed; review /tmp/ultraaudio-install.log')
        print('[OK] Installation and component checks completed.')
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


if __name__ == '__main__':
    try:
        installer_main(sys.argv[1:])
    except Exception as error:
        print('[ERROR] ' + str(error), file=sys.stderr)
        sys.exit(1)
