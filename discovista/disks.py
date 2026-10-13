"""Información de discos, particiones, volúmenes y puntos de montaje."""
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

LSBLK_COLS = ("NAME,PATH,SIZE,TYPE,FSTYPE,FSVER,MOUNTPOINTS,LABEL,PARTLABEL,MODEL,VENDOR,"
              "TRAN,RM,ROTA,FSUSED,FSSIZE,FSAVAIL,UUID")

NETWORK_FS = {"nfs", "nfs4", "cifs", "smb3", "smbfs", "fuse.sshfs", "fuse.rclone", "9p",
              "virtiofs", "zfs", "fuseblk", "fuse.s3fs", "davfs", "fuse.mergerfs"}

TYPE_NAMES = {
    "disk": "Disco", "part": "Partición", "crypt": "Volumen cifrado (LUKS)",
    "lvm": "Volumen lógico (LVM)", "raid0": "RAID 0", "raid1": "RAID 1", "raid5": "RAID 5",
    "raid6": "RAID 6", "raid10": "RAID 10", "rom": "Unidad óptica", "md": "RAID",
}

FS_NAMES = {
    "vfat": "FAT32", "ntfs": "NTFS", "exfat": "exFAT", "ext4": "ext4", "ext3": "ext3", "ext2": "ext2",
    "btrfs": "Btrfs", "xfs": "XFS", "swap": "swap", "crypto_LUKS": "LUKS (cifrado)",
    "LVM2_member": "LVM", "f2fs": "F2FS", "zfs_member": "ZFS", "iso9660": "ISO 9660",
}


@dataclass
class Mount:
    mountpoint: str
    fstype: str
    source: str


@dataclass
class Volume:
    """Una partición, volumen lógico, volumen cifrado o sistema de archivos."""
    name: str
    path: str
    type: str
    size: int
    fstype: str = ""
    label: str = ""
    mountpoints: list = field(default_factory=list)
    used: int = None
    total: int = None
    level: int = 0
    children: list = field(default_factory=list)
    uuid: str = ""

    @property
    def mounted(self):
        return bool(self.mountpoints)

    @property
    def title(self):
        if self.label:
            return self.label
        if self.mountpoints:
            return self.mountpoints[0]
        return self.name

    @property
    def fs_name(self):
        return FS_NAMES.get(self.fstype, self.fstype or "sin formato")

    @property
    def type_name(self):
        return TYPE_NAMES.get(self.type, self.type)


@dataclass
class Disk:
    name: str
    path: str
    size: int
    model: str
    transport: str
    removable: bool
    rotational: bool
    volumes: list          # nivel superior (particiones)
    whole: Volume = None   # disco formateado sin tabla de particiones

    @property
    def kind_name(self):
        if self.transport == "usb" or self.removable:
            return "Disco extraíble"
        if self.transport == "nvme" or self.name.startswith("nvme"):
            return "SSD NVMe"
        if self.name.startswith("mmcblk"):
            return "Tarjeta SD / eMMC"
        if self.rotational:
            return "Disco duro (HDD)"
        return "SSD"

    def all_volumes(self):
        out = []

        def walk(vs):
            for v in vs:
                out.append(v)
                walk(v.children)
        walk([self.whole] if self.whole else self.volumes)
        return out


_esc = re.compile(r"\\([0-7]{3})")


def _unescape(s):
    return _esc.sub(lambda m: chr(int(m.group(1), 8)), s)


def read_mounts():
    mounts = []
    try:
        with open("/proc/self/mountinfo", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                try:
                    sep = parts.index("-")
                except ValueError:
                    continue
                mounts.append(Mount(_unescape(parts[4]), parts[sep + 1], _unescape(parts[sep + 2])))
    except OSError:
        pass
    return mounts


def mountpoints():
    return [m.mountpoint for m in read_mounts()]


def mount_for_path(path, mounts=None):
    mounts = mounts or read_mounts()
    best = None
    for m in mounts:
        mp = m.mountpoint
        if path == mp or path.startswith(mp.rstrip("/") + "/"):
            if best is None or len(mp) >= len(best.mountpoint):
                best = m
    return best


def _usage(mp):
    try:
        u = shutil.disk_usage(mp)
        return u.used, u.total
    except OSError:
        return None, None


def _volume(d, level):
    mps = [m for m in (d.get("mountpoints") or []) if m]
    v = Volume(
        name=d.get("name") or "", path=d.get("path") or "", type=d.get("type") or "",
        size=int(d.get("size") or 0), fstype=d.get("fstype") or "",
        label=d.get("label") or d.get("partlabel") or "", mountpoints=mps, level=level,
        uuid=d.get("uuid") or "",
    )
    if mps and v.fstype != "swap":
        v.used, v.total = _usage(mps[0])
    elif d.get("fsused") is not None:
        v.used = int(d.get("fsused") or 0)
        v.total = int(d.get("fssize") or 0) or None
    v.children = [_volume(c, level + 1) for c in d.get("children") or []]
    return v


def list_disks():
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-o", LSBLK_COLS], capture_output=True,
                             text=True, timeout=10).stdout
        data = json.loads(out).get("blockdevices", [])
    except Exception:
        data = []
    disks = []
    for d in data:
        if d.get("type") not in ("disk", "rom") or not int(d.get("size") or 0):
            continue
        if d.get("name", "").startswith(("zram", "loop")):
            continue
        vendor = (d.get("vendor") or "").strip()
        if vendor.upper() == "ATA":
            vendor = ""
        model = " ".join(x for x in (vendor, (d.get("model") or "").strip()) if x)
        disk = Disk(
            name=d.get("name"), path=d.get("path"), size=int(d.get("size") or 0),
            model=model or d.get("name"), transport=d.get("tran") or "",
            removable=bool(d.get("rm")), rotational=bool(d.get("rota")),
            volumes=[_volume(c, 0) for c in d.get("children") or []],
        )
        if not disk.volumes and (d.get("fstype") or d.get("mountpoints")):
            disk.whole = _volume(d, 0)
        disks.append(disk)
    return disks


def other_volumes(disks):
    """Volúmenes montados que no son particiones locales (red, FUSE, ZFS...)."""
    known = {v.path for d in disks for v in d.all_volumes()}
    out = []
    for m in read_mounts():
        if m.fstype in NETWORK_FS or (m.fstype.startswith("fuse.") and m.fstype not in
                                       ("fuse.portal", "fuse.gvfsd-fuse")):
            if m.source in known:
                continue
            used, total = _usage(m.mountpoint)
            out.append(Volume(name=os.path.basename(m.mountpoint) or m.mountpoint,
                              path=m.source, type="net", size=total or 0, fstype=m.fstype,
                              label="", mountpoints=[m.mountpoint], used=used, total=total))
    return out


def locate(path, disks):
    """Devuelve (mount, volumen, disco) donde está la ruta."""
    m = mount_for_path(path)
    if not m:
        return None, None, None
    src = os.path.realpath(m.source) if m.source.startswith("/dev/") else m.source
    for d in disks:
        for v in d.all_volumes():
            if v.path and (v.path == m.source or os.path.realpath(v.path) == src):
                return m, v, d
    return m, None, None
