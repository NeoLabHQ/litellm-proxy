FROM ghcr.io/berriai/litellm:main-latest

WORKDIR /app

COPY config.yaml /app/config.yaml

EXPOSE 4000

CMD ["--config", "/app/config.yaml", "--detailed_debug"]
