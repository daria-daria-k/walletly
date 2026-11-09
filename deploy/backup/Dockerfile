FROM postgres:17-alpine
RUN apk add --no-cache gnupg rclone
COPY backup-loop.sh decrypt.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/backup-loop.sh /usr/local/bin/decrypt.sh
