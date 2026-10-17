FROM authelia/authelia:4.39.28
# Baked in rather than bind-mounted: Komodo's clone doesn't provide repo files to bind mounts (the dashy lesson).
# /config stays a volume for the SQLite DB and notification.txt.
COPY configuration.yml /etc/authelia/configuration.yml
