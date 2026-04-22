FROM python:3.12-slim

# APP_ENV is baked in at build time from the deploy workflow input.
# Default is 'local' for developer builds.
ARG APP_ENV=local
ENV APP_ENV=${APP_ENV}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
