FROM python:3.11-slim

# LightGBM needs the OpenMP runtime (libgomp1); the slim image doesn't ship it.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the app (data/raw and auth_config.yaml are gitignored, so never shipped)
COPY . .

# Hugging Face Spaces runs containers as a non-root user (UID 1000)
RUN useradd -m -u 1000 user && chown -R user:user /app
USER user

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
