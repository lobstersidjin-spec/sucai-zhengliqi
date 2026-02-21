# 点点素材管理大师 - Docker 镜像（NAS 后台监控 + 自动拷贝）
FROM python:3.11-slim

ARG VERSION=0.7
LABEL org.opencontainers.image.title="点点素材管理大师" \
      org.opencontainers.image.version="${VERSION}"

WORKDIR /app

# 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用
COPY media_organizer.py .
COPY daemon.py .
COPY config.json .
COPY device_suffixes.json .

ENV CONFIG_DIR=/data
ENV PYTHONUNBUFFERED=1

VOLUME ["/data", "/media"]

CMD ["python", "-u", "daemon.py"]
