#!/usr/bin/env python3
"""Register this checkout without overwriting an existing skill."""
import argparse
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent

def install(target, copy=False):
    dest=Path(target).expanduser().absolute()/'job-scout'
    if dest.exists() or dest.is_symlink():
        if dest.resolve()==ROOT:
            return dest
        raise ValueError(f'目标已存在，未覆盖：{dest}。先自行备份/选择其他目标。')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if copy:
        if dest.is_relative_to(ROOT):
            raise ValueError('不能把副本放进当前源码目录内部')
        from build_package import release_files
        for src in release_files():
            dst=dest/src.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    else:
        dest.symlink_to(ROOT,target_is_directory=True)
    return dest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',required=True,help='宿主的 skills 目录，不是 job-scout 目录')
    p.add_argument('--copy',action='store_true',help='用副本替代符号链接；安装依赖需在副本中重新执行')
    args=p.parse_args()
    try:print(install(args.target,args.copy))
    except (OSError,ValueError) as e:p.exit(2,str(e)+'\n')
