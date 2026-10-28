#!/usr/bin/env python3
"""Recover the exact source trees from the verified runtime packages for CI/rebuilds."""
import io
from pathlib import Path
import tarfile
from prepare_release import BASE, inspect_package, members


def unpack():
    for filename, folder in [('Ultra_Audio_Final_V1.ipk', 'ipk-source'),
                             ('Ultra_Audio_Final_DreamOS.deb', 'deb-source')]:
        package = BASE / 'packages' / filename
        inspect_package(package)
        target = BASE / folder
        if target.exists():
            raise ValueError('Source directory already exists; use a fresh checkout: ' + folder)
        parts = members(package.read_bytes())
        for member_name, subtree in [('control.tar.gz', 'control'), ('data.tar.gz', 'data')]:
            with tarfile.open(fileobj=io.BytesIO(parts[member_name]), mode='r:gz') as archive:
                for item in archive:
                    relative = Path(item.name)
                    if relative.is_absolute() or '..' in relative.parts or not (item.isfile() or item.isdir()):
                        raise ValueError('Unsafe package source entry')
                    path = target / subtree / relative
                    if item.isdir():
                        path.mkdir(parents=True, exist_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(archive.extractfile(item).read())
                        path.chmod(item.mode & 0o777)
        print('Recovered verified sources: ' + folder)


if __name__ == '__main__':
    unpack()
