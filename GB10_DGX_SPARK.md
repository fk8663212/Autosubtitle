# GB10 / DGX Spark 安裝指南

本文件適用於 NVIDIA GB10／DGX Spark。一般電腦請參考 [README.md](README.md)。

GB10 是 ARM64 Grace Blackwell 平台。建議使用 NVIDIA NGC PyTorch 容器，以取得相容的 CUDA、PyTorch 與 ARM64 環境。

## 環境需求

- NVIDIA GB10／DGX Spark
- Docker
- NVIDIA Container Toolkit

確認 GPU 與 Docker 工具：

```bash
nvidia-smi
docker --version
nvidia-ctk --version
```

## 建置映像

本專案使用 `nvcr.io/nvidia/pytorch:25.11-py3`，提供 ARM64 映像及 CUDA 13.0 環境。Dockerfile 也會安裝 Whisper 所需的 `ffmpeg`。

```bash
sudo docker build --no-cache -t autosubtitle-gb10 .
```

驗證 PyTorch 能辨識 GB10：

```bash
sudo docker run --rm --gpus all \
  --entrypoint python autosubtitle-gb10 \
  -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

預期輸出包含：

```text
True NVIDIA GB10
```

## 產生原文字幕

```bash
sudo docker run --rm --gpus all \
  -v "$PWD/videos:/data" \
  -v "$HOME/.cache/whisper:/root/.cache/whisper" \
  autosubtitle-gb10 /data
```

第一次執行會下載 Whisper 模型。預設使用 CUDA 與 FP16。

若字幕已存在並需要重新產生：

```bash
sudo docker run --rm --gpus all \
  -v "$PWD/videos:/data" \
  -v "$HOME/.cache/whisper:/root/.cache/whisper" \
  autosubtitle-gb10 /data --overwrite
```

## 使用 LLM 翻譯

翻譯模型與 API／本地模式由 `config.toml` 設定。若影片旁邊已有同名 `.srt`，`--translate` 會直接翻譯既有字幕並跳過 Whisper。

### 本地模型

本地 Ollama 或 vLLM 執行在主機時，使用 host network：

```bash
sudo docker run --rm --gpus all \
  --network host \
  -v "$PWD/videos:/data" \
  -v "$HOME/.cache/whisper:/root/.cache/whisper" \
  -v "$PWD/config.toml:/workspace/Autosubtitle/config.toml:ro" \
  autosubtitle-gb10 /data --translate --overwrite
```

### 只翻譯現有 SRT

如果已經有英文 `.srt`，可以不跑 Whisper，直接翻譯字幕檔：

```bash
sudo docker run --rm --gpus all \
  --network host \
  -v "$PWD/videos:/data" \
  -v "$PWD/config.toml:/workspace/Autosubtitle/config.toml:ro" \
  autosubtitle-gb10 /data --translate-srt --recursive
```

單一字幕檔也可以：

```bash
sudo docker run --rm --gpus all \
  --network host \
  -v "$PWD/videos:/data" \
  -v "$PWD/config.toml:/workspace/Autosubtitle/config.toml:ro" \
  autosubtitle-gb10 "/data/demo.srt" --translate-srt
```

輸出檔名會像 `demo.zh-TW.srt`。

### API 模型

API 金鑰透過環境變數傳入，不要寫進 `config.toml`：

```bash
export OPENAI_API_KEY="你的金鑰"

sudo docker run --rm --gpus all \
  -e OPENAI_API_KEY \
  -v "$PWD/videos:/data" \
  -v "$HOME/.cache/whisper:/root/.cache/whisper" \
  -v "$PWD/config.toml:/workspace/Autosubtitle/config.toml:ro" \
  autosubtitle-gb10 /data --translate --overwrite
```

## 背景監看資料夾

持續監看 `videos` 與其子資料夾：

```bash
sudo docker run -d \
  --name autosubtitle-watch \
  --restart unless-stopped \
  --gpus all \
  -v "$PWD/videos:/data" \
  -v "$HOME/.cache/whisper:/root/.cache/whisper" \
  autosubtitle-gb10 /data --watch --recursive
```

查看日誌：

```bash
sudo docker logs -f autosubtitle-watch
```

停止並移除服務：

```bash
sudo docker stop autosubtitle-watch
sudo docker rm autosubtitle-watch
```

監看時使用主機上的本地 LLM，需額外加入：

```text
--network host
-v "$PWD/config.toml:/workspace/Autosubtitle/config.toml:ro"
```

並在程式參數最後加入 `--translate`。

## 常見問題

### Docker socket 權限不足

本文件的 Docker 指令已使用 `sudo`。若帳號已加入 `docker` 群組，可自行省略。

### 容器找不到 ffmpeg

請重新建置最新映像：

```bash
sudo docker build --no-cache -t autosubtitle-gb10 .
```

### CUDA 無法使用

先執行本文件的 PyTorch GPU 驗證指令，確認輸出為 `True NVIDIA GB10`。若失敗，再檢查 NVIDIA 驅動與 Container Toolkit。
