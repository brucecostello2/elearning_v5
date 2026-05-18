beat_schedule.update({
    # Retention lifecycle: evaluate all assets against policies, migrate tiers
    "retention-lifecycle-daily": {
        "task": "app.tasks.retention_lifecycle.run_lifecycle",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": "default"},
    },
    # Orphan scan: filer walk + DB cross-reference + quarantine
    "orphan-scan-daily": {
        "task": "app.tasks.orphan_scan.run_orphan_scan",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "default"},
    },
    # NAS backup: pg_dump + rsync to /mnt/backup
    "backup-snapshot-nightly": {
        "task": "app.tasks.backup_snapshot.run_backup",
        "schedule": crontab(hour=2, minute=30),
        "options": {"queue": "default"},
    },
    # Capacity analytics: per-tier utilisation + Prometheus metrics
    "capacity-analytics-nightly": {
        "task": "app.tasks.capacity_analytics.run_analytics",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "default"},
    },
    # Quota enforcement: sync used_bytes from DB, check thresholds
    "quota-enforcement-hourly": {
        "task": "app.tasks.quota_enforcement.run_enforcement",
        "schedule": crontab(minute=0),
        "options": {"queue": "default"},
    },
})
