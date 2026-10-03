# The Render image is separate from the Windows localhost launcher.
FROM node:22-bookworm-slim AS dashboard
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# Firebase web configuration is public, not a Firebase service-account key.
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_APP_ID
ARG VITE_FIREBASE_STORAGE_BUCKET
ARG VITE_FIREBASE_MESSAGING_SENDER_ID
RUN npm run build:render

FROM ollama/ollama:0.34.2 AS ollama
# Render uses CPU inference. Keep the CPU runner and libraries without copying
# several GB of CUDA/Vulkan payloads into the final image and build disk.
RUN mkdir -p /cpu/lib && find /usr/lib/ollama -mindepth 1 -maxdepth 1 ! -type d \
    -exec cp -a -t /cpu/lib {} +

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NODE_ENV=production \
    ANONYMIZED_TELEMETRY=False
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx apache2-utils ca-certificates libgomp1 libstdc++6 libopenblas0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=dashboard /usr/local/bin/node /usr/local/bin/node
# Ollama resolves its inference helper relative to ../lib/ollama. Preserve the
# upstream /usr/bin + /usr/lib layout; /api/tags alone cannot detect a bad layout.
COPY --from=ollama /bin/ollama /usr/bin/ollama
COPY --from=ollama /cpu/lib /usr/lib/ollama
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ /app/backend/
COPY ml/ /app/ml/
COPY deploy/render/ /app/deploy/render/
COPY --from=dashboard /build/frontend/dist-render/ /app/frontend/dist-render/
COPY extension/ /app/extension/
RUN python deploy/render/package_extension.py /app/extension /app/chaigaram-extension.zip
EXPOSE 10000
CMD ["python", "deploy/render/start.py"]
