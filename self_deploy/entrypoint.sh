#!/bin/bash
# Ensure data dirs exist and are writable by the council user
# This runs as root BEFORE dropping to the council user,
# so it fixes permissions on volume-mounted directories.
mkdir -p /app/data/brain /app/data/bag /app/data/workflows /app/data/slots /app/data/config /app/capsule
chown -R council:council /app/data /app/capsule

# Drop to council user and run the server
exec su -s /bin/bash council -c "python backend/server.py"
