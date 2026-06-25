FROM nvcr.io/nvidia/pytorch:25.11-py3

ENV PYTHONUNBUFFERED=1

WORKDIR /workspace/Autosubtitle

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg \
    && ffmpeg -version \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY autosubtitle ./autosubtitle
COPY main.py ./main.py
COPY config.toml ./config.toml

ENTRYPOINT ["python", "main.py"]
