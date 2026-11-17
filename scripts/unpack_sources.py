#!/usr/bin/env python3
"""Recover the exact source trees from the verified runtime packages for CI/rebuilds."""
import io
from pathlib import Path
import tarfile
from prepare_release import BASE, inspect_package, members
from release_variants import VARIANTS


def unpack():
    for family, channel, filename, manifest in VARIANTS:
        folder = ('dreambox-' if family == 'dreambox-one-two' else '') + ('deb-source' if channel == 'dreamos' else 'ipk-source')
        package = BASE / 'packages' / filename
        inspect_package(package)
        target = BASE / folder
        if target.exists():
            raise ValueError('Source directory already exists; use a fresh checkout: ' + folder)
        parts = members(package.read_bytes())
        for subtree in ('control', 'data'):
            member_name = next(x for x in parts if x.startswith(subtree + '.tar.'))
            with tarfile.open(fileobj=io.BytesIO(parts[member_name]), mode='r:*') as archive:
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
