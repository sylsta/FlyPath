#!/usr/bin/env bash
echo "== Desktop environment =="
echo "XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP"
echo "XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
echo

echo "== How is QGIS installed? (matters: flatpak/snap sandbox subprocess/paths) =="
which qgis 2>/dev/null
snap list 2>/dev/null | grep -i qgis
flatpak list 2>/dev/null | grep -i qgis
echo

echo "== Required binaries on PATH =="
for bin in gio kioclient5 udevadm pgrep; do
    printf '%-12s: ' "$bin"
    which "$bin" 2>/dev/null || echo "NOT FOUND"
done
echo

echo "== Processes =="
pgrep -a kiod5
pgrep -a gvfsd-mtp
echo "(empty above = process not running)"
echo

echo "== gio mount -l (should list the RC as an MTP volume/mount) =="
gio mount -l 2>&1
echo

echo "== gvfs mount directories for this user =="
echo "UID=$(id -u)"
ls -la "/run/user/$(id -u)/gvfs/" 2>&1
ls -la "/run/user/$(id -u)/gvfsd/" 2>&1
echo

echo "== udevadm view of connected MTP-capable USB devices =="
udevadm info --export-db 2>/dev/null | grep -B5 "ID_MTP_DEVICE=1"
