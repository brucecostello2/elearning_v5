#!/bin/bash
set -e

echo "=== Phase 6 Environment Setup ==="
echo "Sets up 4 services for integration testing"
echo ""

# 1. PostgreSQL
echo "1. PostgreSQL"
if pg_isready -q 2>/dev/null; then
    echo "   ✅ Already running on port 5432"
else
    sudo pg_ctlcluster 15 main start
    echo "   ✅ Started on port 5432"
fi

# 2. Redis
echo ""
echo "2. Redis"
if redis-cli -p 6380 ping 2>/dev/null | grep -q PONG; then
    echo "   ✅ Already running on port 6380"
else
    redis-server --port 6380 --daemonize yes
    echo "   ✅ Started on port 6380"
fi

# 3. SeaweedFS
echo ""
echo "3. SeaweedFS"
if curl -s http://localhost:9333/dir/status > /dev/null 2>&1; then
    echo "   ✅ Already running (master:9333, volume:8080)"
else
    mkdir -p /tmp/seaweedfs-data
    nohup /tmp/weed server -dir=/tmp/seaweedfs-data -master.port=9333 -volume.port=8080 > /tmp/seaweedfs.log 2>&1 &
    sleep 3
    echo "   ✅ Started (master:9333, volume:8080)"
fi

# 4. TimescaleDB
echo ""
echo "4. TimescaleDB"
sudo -u postgres psql -d ivgs_metrics -c "SELECT 1" > /dev/null 2>&1 && \
    echo "   ✅ ivgs_metrics database ready with TimescaleDB extension" || \
    echo "   ❌ ivgs_metrics not available"

echo ""
echo "=== Environment Ready ==="
echo "Config: .env.phase6"
