#!/bin/sh
# Fills in secrets that can't be committed (the repo is public) before Dashy starts.
# MONITORING_BASIC_AUTH: base64 of "uptime-kuma:<password>", the LLDAP monitoring account that
# status checks use to get through Authelia forward-auth. Comes from env_file
# /home/nelson/containers/dashy/.env on nelson-nuc.
CONF=/app/user-data/conf.yml
if [ -n "$MONITORING_BASIC_AUTH" ]; then
  sed -i "s|__MONITORING_BASIC_AUTH__|$MONITORING_BASIC_AUTH|g" "$CONF"
else
  echo "dashy-start: MONITORING_BASIC_AUTH not set; status checks behind Authelia will fail" >&2
fi
exec node server.js
