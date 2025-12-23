#!/bin/bash
set -e

if [ "$1" = "gunicorn" ]; then
  shift
  cd /var/www
  python3 manage.py migrate --noinput
  exec gunicorn "$@"

elif [ "$1" = "celery" ]; then
  shift
  cd /var/www
  exec celery "$@"

elif [ "$1" = "nginx" ]; then
  cd /var/www
  python3 manage.py collectstatic --noinput

  cat >/etc/nginx/sites-available/default <<'EOL'
server {
    listen 80;

    client_max_body_size 200M;
    client_body_timeout 300s;
    client_body_buffer_size 32k;

    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300s;
        proxy_send_timeout 300s;

        proxy_pass http://app:9090;
    }

    location /static/ {
        alias /var/www/static/;
    }
}
EOL

  cat >/etc/nginx/nginx.conf <<'EOL'
user root;
worker_processes auto;
pid /run/nginx.pid;
error_log /dev/stderr warn;

daemon off;

events { worker_connections 1024; }

http {
    error_log /dev/stderr warn;
    access_log /dev/stdout;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;

    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    gzip on;

    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
EOL

  exec nginx

elif [ "$1" = "manage.py" ]; then
  shift
  cd /var/www
  exec python3 manage.py "$@"

elif [ "$1" = "bash" ]; then
  exec bash

else
  exec "$@"
fi
