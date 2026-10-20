FROM python:3.12-slim
WORKDIR /app
# ultralytics تسحب opencv-python التي تحتاج مكتبات النظام هذه
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-ai.txt ./
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch torchvision \
 && pip install --no-cache-dir -r requirements-ai.txt
COPY backend backend
COPY frontend frontend
COPY config config
RUN python -m backend.models
ENV DARB_DATA_DIR=/data
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
