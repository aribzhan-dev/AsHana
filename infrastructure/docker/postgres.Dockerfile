FROM postgres:17-alpine
COPY --chmod=0644 infrastructure/docker/init-db.sh /docker-entrypoint-initdb.d/10-ashana.sh
