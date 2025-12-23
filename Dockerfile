FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    nginx \
    curl \
    ca-certificates \
    git \
    postgresql-client \
  && rm -rf /var/lib/apt/lists/* \
  && mkdir -p /var/www

RUN curl -fsSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc \
  && chmod +x /usr/local/bin/mc

WORKDIR /var/www

COPY requirements.txt /var/www/requirements.txt
RUN pip install --no-cache-dir -r /var/www/requirements.txt

COPY . /var/www

RUN chmod +x /var/www/entrypoint.sh

EXPOSE 80
ENTRYPOINT ["/var/www/entrypoint.sh"]
