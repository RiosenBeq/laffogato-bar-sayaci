# LAFFOGATO — container ile çalıştırma (isteğe bağlı).
# Mac/Windows'ta Docker Desktop ile de çalışır AMA bilgisayarın kendi kamerası
# container içinden GÖRÜLEMEZ (Docker Desktop USB/kamera geçirmez).
# Container içinde kaynak olarak RTSP adresi veya video dosyası kullanın.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libsm6 libxext6 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /uygulama

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY models/ models/
# Model dosyası olmadan container sessizce "tespit yapmayan" bir sisteme
# dönüşürdü. Derleme burada, ANLAŞILIR bir mesajla durur.
RUN test -s models/yolox_tiny.onnx || ( \
      echo "" && \
      echo "HATA: models/yolox_tiny.onnx bulunamadi." && \
      echo "Cozum: imaji derlemeden ONCE su komutu calistirin:" && \
      echo "        bash models/indir.sh" && \
      echo "" && exit 1 )


ENV PYTHONUNBUFFERED=1
EXPOSE 8100

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
