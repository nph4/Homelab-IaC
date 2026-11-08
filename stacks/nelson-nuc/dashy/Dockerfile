FROM lissy93/dashy:4.7.0
# Owned by node so dashy-start.sh (running as node) can fill in secrets at startup
COPY --chown=node:node my-config.yml /app/user-data/conf.yml
COPY --chmod=755 dashy-start.sh /app/dashy-start.sh
CMD ["/app/dashy-start.sh"]
