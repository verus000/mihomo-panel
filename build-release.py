#!/usr/bin/env python3
"""Build a source-only release from an explicit allowlist, excluding all live data."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys
import tarfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('panel_deployment',ROOT/'deploy/cli.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


def build(output):
    version=(ROOT/'VERSION').read_text().strip()
    output.mkdir(parents=True,exist_ok=True)
    path=output/f'mihomo-panel-{version}.tar.gz'
    files=[]
    for name in module.ITEMS:
        member=ROOT/name
        if member.is_symlink():raise ValueError('Release members must not be symlinks')
        files += [member] if member.is_file() else sorted(x for x in member.rglob('*') if x.is_file() and not any(p in ('__pycache__','.pytest_cache') for p in x.parts))
    with tarfile.open(path,'w:gz') as archive:
        for member in files:
            if member.is_symlink():raise ValueError('Release members must not be symlinks')
            relative=member.relative_to(ROOT)
            if member.suffix in ('.sqlite3','.env','.dump') or '.sqlite3-' in member.name:
                raise ValueError('Unexpected data file in release: '+str(relative))
            archive.add(member,arcname=f'mihomo-panel-{version}/{relative}',recursive=False)
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    sums=output/(path.name+'.sha256')
    sums.write_text(checksum+'  '+path.name+'\n')
    print(path)
    print(sums)
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    build(parser.parse_args().output)
