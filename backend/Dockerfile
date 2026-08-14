# 活动策划后端生产镜像
#
# 注意：
#   - sentence-transformers 依赖 CPU 版 torch，镜像较大（~2-3GB），首次构建较慢
#   - 国内网络拉 pip 慢时，可加 build 参数换镜像源：
#       docker compose -f compose.prod.yml build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple backend
#   - BGE embedding 模型首次调用时从 HuggingFace 下载（可用 HF_ENDPOINT 镜像，见 .env）
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# pymilvus 2.4.x 运行时依赖 pkg_resources（setuptools>=81 已移除）→ 先固定 <81
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" "setuptools<81"

WORKDIR /app

COPY requirements.txt ./
# 先装 CPU 版 torch：默认 pypi 的 torch 是 CUDA 构建，会额外拉数 GB 的 nvidia-* 库；
# BGE embedding 是纯 CPU 推理，用不到 CUDA。CPU 版装好后，
# requirements 里的 sentence-transformers 依赖自动被满足，不会再拉 CUDA 版 torch。
# 国内慢可换：--build-arg TORCH_INDEX_URL=https://mirrors.aliyun.com/pytorch-wheels/cpu
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --index-url "$TORCH_INDEX_URL" torch
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

COPY backend ./backend

# 非 root 运行（安全加固）
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# worker 数由 compose 的 command 覆盖（--workers N）；这里默认单进程兜底
CMD ["uvicorn", "backend.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
