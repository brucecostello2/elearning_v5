# Host configuration not managed by Docker

## /etc/tmpfiles.d/ivgs.conf
Creates /run/ivgs owned by uid/gid 999 on every boot. The backup-worker
bind-mounts this path and writes its lock file there as user `ivgs` (999).
Without it, backup.sh and asset_backup.sh fail with "Permission denied"
on the lock file. Install with:

    cp configs/systemd/ivgs-tmpfiles.conf /etc/tmpfiles.d/ivgs.conf
    systemd-tmpfiles --create /etc/tmpfiles.d/ivgs.conf

## /etc/fstab NFS mount
    192.168.1.7:/mnt/store/ivgs  /mnt/backup/ivgs  nfs  vers=4,hard,timeo=600,_netdev,nofail  0  0

Archive share (image artifacts), mounted on demand:
    192.168.1.7:/mnt/store/ivgs-archive  /mnt/ivgs-archive  nfs  vers=4,hard,timeo=600,_netdev,nofail  0  0

Replaced //192.168.1.9/elearning (CIFS) on 2026-08-14. The .9 share was
100% full and is retained read-only as fallback until two clean cycles
have run on .7.
