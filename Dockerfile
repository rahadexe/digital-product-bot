# ---- Admin panel (static export) ----
FROM node:22-alpine AS console
WORKDIR /console
COPY console/package.json ./
RUN npm install
COPY console/ ./
RUN npm run build

# ---- Bot, API and workers ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Container defaults, so the deployment only has to provide secrets and the public address.
ENV APP_ENV=production HOST=0.0.0.0 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY --from=console /console/out ./console/out
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"
CMD ["python", "-m", "app"]
