FROM ghcr.io/berriai/litellm:main-v1.83.7-stable

WORKDIR /app

COPY config.yaml /app/config.yaml

EXPOSE 4000

CMD ["--config", "/app/config.yaml", "--detailed_debug"]
