# Hosted (phone/browser) version. Build: docker build -t nodal .   Run: docker run -p 7860:7860 -e NODAL_SECRET=... nodal
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# bake the face model into the image so start-up needs no download
RUN python -c "from insightface.app import FaceAnalysis; a=FaceAnalysis(name='buffalo_l',root='/app/models',providers=['CPUExecutionProvider']); a.prepare(ctx_id=-1)"
COPY . .
# Hugging Face runs the container as a non-root user: code and models must be readable, the data folder writable
RUN chmod -R a+rX /app && mkdir -p /tmp/nodal && chmod 777 /tmp/nodal
ENV NODAL_MODE=hosted NODAL_HTTPS=1 NODAL_MODEL_DIR=/app/models NODAL_DATA_DIR=/tmp/nodal PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
