FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN touch README.md && uv sync --frozen --no-dev

COPY docker/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV LOCALOSTACK_HOST=0.0.0.0

EXPOSE 5000 8774 9696 9292 8776

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["localostack"]
