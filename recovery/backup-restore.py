#!/usr/bin/env python3
"""Bulldog Recovery: private backup, validation and guarded restore. No secrets in GitHub."""
import argparse, hashlib, io, json, os, sys, tarfile, tempfile
from pathlib import Path, PurePosixPath
LIMIT = 512 * 1024 * 1024
def sha(data): return hashlib.sha256(data).hexdigest()
def collect(home):
    base=home/"eldoret-connector"
    env=home/".config"/"eldoret.env"
    if not base.is_dir() or not env.is_file() or env.is_symlink():
        raise ValueError("Current Eldoret directory or private .config/eldoret.env missing")
    yield "private/eldoret.env",env
    for p in sorted(base.rglob("*")):
        rel=p.relative_to(base)
        if any(v in (".git","__pycache__",".cache","node_modules") for v in rel.parts): continue
        if p.is_symlink(): continue
        if p.is_file() and p.name not in ("connector.py","manager.py") and not p.name.endswith((".pyc",".tmp",".new")):
            yield "private/eldoret-connector/"+rel.as_posix(),p
def backup(home,out):
    home=Path(home).expanduser().resolve();out=Path(out).expanduser().absolute()
    if out.exists(): raise ValueError("Refusing to overwrite existing backup")
    out.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".bulldog-",dir=out.parent);os.close(fd);os.chmod(tmp,0o600)
    try:
        manifest={};total=0
        with tarfile.open(tmp,"w:gz") as archive:
            for name,p in collect(home):
                data=p.read_bytes();total+=len(data)
                if len(data)>LIMIT or total>LIMIT: raise ValueError("Backup exceeds safety limit")
                manifest[name]={"sha256":sha(data),"size":len(data)}
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600
                archive.addfile(info,io.BytesIO(data))
            data=json.dumps({"format":"bulldog-private-v1","files":manifest},sort_keys=True).encode()
            info=tarfile.TarInfo("manifest.json");info.size=len(data);info.mode=0o600
            archive.addfile(info,io.BytesIO(data))
        os.replace(tmp,out);os.chmod(out,0o600)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    print("PRIVATE BACKUP:",out,"files:",len(manifest),"sha256:",sha(out.read_bytes()))
    print("Contains credentials. Copy to encrypted storage on Mac; verify copied file.")
def validate(path):
    path=Path(path).expanduser().resolve()
    if path.stat().st_size>LIMIT:raise ValueError("Compressed backup too large")
    with tarfile.open(path,"r:gz") as arc:
        entries=arc.getmembers();names=[m.name for m in entries]
        if len(names)!=len(set(names)) or "manifest.json" not in names:raise ValueError("Duplicate/missing archive entries")
        if any(not m.isfile() for m in entries):raise ValueError("Archive contains links or special files")
        info=arc.getmember("manifest.json")
        if info.size>1048576:raise ValueError("Manifest too large")
        manifest=json.load(arc.extractfile(info))
        files=manifest.get("files")
        if manifest.get("format")!="bulldog-private-v1" or not isinstance(files,dict) or set(names)!=(set(files)|{"manifest.json"}):
            raise ValueError("Archive manifest mismatch")
        if "private/eldoret.env" not in files:raise ValueError("No environment credentials")
        total=0
        for name,meta in files.items():
            parts=PurePosixPath(name)
            if (parts.is_absolute() or ".." in parts.parts or name!=parts.as_posix()
                or not (name=="private/eldoret.env" or name.startswith("private/eldoret-connector/"))):
                raise ValueError("Unsafe file name in backup")
            member=arc.getmember(name);total+=member.size
            if total>LIMIT:raise ValueError("Expanded backup too large")
            data=arc.extractfile(member).read(LIMIT+1)
            if len(data)!=member.size or meta.get("size")!=len(data) or meta.get("sha256")!=sha(data):
                raise ValueError("Backup checksum mismatch: "+name)
    print("VERIFIED:",path,"files:",len(files))
    return files
def restore(path,home):
    files=validate(path);home=Path(home).expanduser().resolve()
    base=home/"eldoret-connector";env=home/".config"/"eldoret.env"
    if env.exists() or (base.exists() and any(base.iterdir())):
        raise ValueError("Existing Eldoret files found. Will not overwrite!")
    with tarfile.open(path,"r:gz") as arc:
        for name in files:
            target=env if name=="private/eldoret.env" else base/name.removeprefix("private/eldoret-connector/")
            if not target.resolve().is_relative_to(home):raise ValueError("Target outside user home")
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            data=arc.extractfile(name).read()
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"wb") as f:f.write(data)
            os.chmod(target,0o600)
    print("RESTORED private data. Code and service must still be installed.")
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="mode",required=True)
    a=sub.add_parser("backup");a.add_argument("--output",required=True);a.add_argument("--home",default=str(Path.home()))
    a=sub.add_parser("verify");a.add_argument("--archive",required=True)
    a=sub.add_parser("restore");a.add_argument("--archive",required=True);a.add_argument("--home",default=str(Path.home()))
    args=p.parse_args()
    try:
        if args.mode=="backup":backup(args.home,args.output)
        elif args.mode=="verify":validate(args.archive)
        else:restore(args.archive,args.home)
    except Exception as e:
        print("RECOVERY FAILED:",e,file=sys.stderr);sys.exit(1)
if __name__=="__main__":main()
