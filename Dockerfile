FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN useradd -m -u 1000 bot && mkdir /data && chown bot:bot /data
USER bot
VOLUME /data

HEALTHCHECK --interval=60s --timeout=5s --start-period=90s \
  CMD python -c "import os,sys,time; sys.exit(0 if time.time()-os.path.getmtime('/data/heartbeat')<180 else 1)"

CMD ["python", "-m", "app.main"]
