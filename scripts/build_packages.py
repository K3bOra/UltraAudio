#!/usr/bin/env python3
"""Rebuild the two prepared source trees as deterministic DEB/IPK archives."""
import gzip
import io
from pathlib import Path
import tarfile

BASE = Path(__file__).resolve().parents[1]
PLUGIN = 'data/usr/lib/enigma2/python/Plugins/Extensions/UltraAudio'


def tar_gz(root):
    result = io.BytesIO()
    with gzip.GzipFile(fileobj=result, mode='wb', mtime=0, filename='') as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.GNU_FORMAT) as archive:
            for path in sorted(root.rglob('*')):
                if path.is_symlink():
                    raise ValueError('Unexpected source symlink: ' + str(path))
                if path.suffix in ('.pyc', '.pyo') or '__pycache__' in path.parts:
                    raise ValueError('Remove interpreter caches before building')
                name = './' + path.relative_to(root).as_posix()
                info = archive.gettarinfo(str(path), arcname=name)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = 'root'
                info.mode = 0o755 if path.is_dir() or path.suffix == '.sh' or path.name in ('preinst', 'postinst', 'prerm', 'postrm') else 0o644
                if path.is_file():
                    with path.open('rb') as handle:
                        archive.addfile(info, handle)
                else:
                    archive.addfile(info)
    return result.getvalue()


def build():
    template = (BASE / 'scripts/updater_template.py').read_text(encoding='utf-8')
    packages = BASE / 'packages'
    packages.mkdir(exist_ok=True)
    for channel, tree, name in [('ipk', 'ipk-source', 'Ultra_Audio_Final_V1.ipk'),
                                ('dreamos', 'deb-source', 'Ultra_Audio_Final_DreamOS.deb')]:
        root = BASE / tree
        (root / PLUGIN / 'updater.py').write_text(template.replace("'__CHANNEL__'", repr(channel)), encoding='utf-8')
        output = io.BytesIO()
        output.write(b'!<arch>\n')
        for member, data in [('debian-binary', b'2.0\n'), ('control.tar.gz', tar_gz(root / 'control')), ('data.tar.gz', tar_gz(root / 'data'))]:
            header = '%-16s%-12d%-6d%-6d%-8s%-10d`\n' % (member + '/', 0, 0, 0, '100644', len(data))
            output.write(header.encode('ascii'))
            output.write(data)
            if len(data) % 2:
                output.write(b'\n')
        (packages / name).write_bytes(output.getvalue())
        print('Built ' + name)


if __name__ == '__main__':
    build()
