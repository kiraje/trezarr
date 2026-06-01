#!/bin/sh
# entrypoint.sh — PUID/PGID drop-privilege entrypoint for Trezarr (INTG-04)
#
# Reads PUID and PGID environment variables (default 1000:1000) and:
#  1. Creates a group with GID=PGID named "trezarr" (if it doesn't exist)
#  2. Creates a user  with UID=PUID named "trezarr" (if it doesn't exist)
#  3. chown -R PUID:PGID /config so the process can read/write the config volume
#  4. exec gosu PUID:PGID "$@" — clean privilege drop; replaces this script's PID
#
# This mirrors the LinuxServer.io PUID/PGID convention used by Sonarr/Radarr/Bazarr,
# ensuring that subtitle sidecars (.vi.srt) written next to media files carry the
# same host user ownership as the rest of the *arr output.
#
# Usage (from Dockerfile):
#   ENTRYPOINT ["/entrypoint.sh"]
#   CMD ["trezarr", "serve"]
#
# Example docker run:
#   docker run -e PUID=$(id -u) -e PGID=$(id -g) ...

set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# Create group if it doesn't already exist with PGID
if ! getent group "$PGID" > /dev/null 2>&1; then
    groupadd --gid "$PGID" trezarr
fi

# Create user if it doesn't already exist with PUID
if ! getent passwd "$PUID" > /dev/null 2>&1; then
    useradd \
        --uid "$PUID" \
        --gid "$PGID" \
        --no-create-home \
        --shell /sbin/nologin \
        trezarr
fi

# Fix /config ownership so the process can write the SQLite DB, config,
# quarantine dir, and log files.
chown -R "${PUID}:${PGID}" /config

# Drop privileges and exec the process (replacing this script's PID).
# gosu handles the uid/gid drop cleanly (no sudo, no su -c weirdness).
exec gosu "${PUID}:${PGID}" "$@"
