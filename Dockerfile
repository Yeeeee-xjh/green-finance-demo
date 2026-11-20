FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装开源中文字体与PDF依赖，清理apt缓存减小镜像
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单，利用Docker缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 确保数据目录存在
RUN mkdir -p green_model/data/phase1 green_model/data/uploads green_model/data/reports

# 暴露端口，云平台会通过PORT环境变量覆盖
ENV PORT=8000
ENV PUBLIC_READONLY=1
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT','8000') + '/health')" || exit 1

# 生产启动命令
CMD ["python", "-m", "green_model.web_app_phase2"]
