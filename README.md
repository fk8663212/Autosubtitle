# Autosubtitle

自動掃描資料夾中的影片檔，並為每支影片產生同名的外掛字幕檔 (`.srt`)。

目前版本使用 OpenAI Whisper 與 PyTorch 做語音辨識，預設只產生原文字幕檔，不執行翻譯。

## 功能

- 掃描指定資料夾中的影片
- 支援遞迴掃描子資料夾
- 為每支影片輸出同名 `.srt`
- 可指定 Whisper 模型大小
- 可指定語言，或交給模型自動判斷
- 預設只輸出 Whisper 辨識原文
- 可選擇啟用既有翻譯模組
- 可選擇是否覆寫既有字幕檔

## 環境需求

- Python 3.11+
- `ffmpeg`

## GB10 / DGX Spark 安裝（建議）

GB10 是 ARM64 Grace Blackwell 平台，建議使用 NVIDIA NGC PyTorch 容器，以取得相容的 CUDA 與 PyTorch：

本專案固定使用 `nvcr.io/nvidia/pytorch:25.11-py3`，其 CUDA 13.0 與目前 GB10 驅動相容，並提供 ARM64 映像。

```bash
sudo docker build --no-cache -t autosubtitle-gb10 .
```

建置時會一併安裝 Whisper 讀取影音所需的 `ffmpeg`。建置後可先確認 PyTorch 是否辨識到 GB10：

```bash
sudo docker run --rm --gpus all \
  --entrypoint python autosubtitle-gb10 \
  -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

預期輸出包含 `True NVIDIA GB10`。

執行時掛載影片資料夾與 Whisper 模型快取：

```bash
sudo docker run --rm --gpus all \
  -v "$PWD/videos:/data" \
  -v "$HOME/.cache/whisper:/root/.cache/whisper" \
  autosubtitle-gb10 /data
```

第一次執行會下載 Whisper 模型。預設使用 CUDA 與 FP16。

## 一般安裝

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用方式

掃描 `videos` 資料夾，為所有影片產生字幕：

```bash
python3 main.py videos
```

預設使用 CUDA 執行辨識；若要改用 CPU，可加上 `--device cpu --compute-type float32`。

指定辨識語言：

```bash
python3 main.py videos --model small --language zh
```

如需暫時啟用既有翻譯模組：

```bash
python3 main.py videos --translate --target-language zh-TW
```

輸出雙語字幕：

```bash
python3 main.py videos --translate --bilingual
```

遞迴掃描並覆寫既有字幕：

```bash
python3 main.py videos --recursive --overwrite
```

## 支援副檔名

預設支援：

- `.mp4`
- `.mkv`
- `.mov`
- `.avi`
- `.m4v`
- `.webm`

## 輸出結果

若輸入檔案為：

```text
videos/demo.mp4
```

則會輸出：

```text
videos/demo.srt
```

預設情況下，`demo.srt` 內容會是 Whisper 辨識出的原文字幕。

## 翻譯說明

- 翻譯預設不啟用
- 加上 `--translate` 才會執行既有翻譯模組
- 翻譯目標語言預設是 `zh-TW`
- 目前翻譯使用 Google Translate 介面，因此執行翻譯時需要網路
- 若加上 `--bilingual`，每個字幕區塊會先放原文，再放翻譯內容
- 若來源語言與目標語言相同，系統會直接保留原字幕文字

## 後續可擴充

- 產生 `.vtt`
- 批次加上雙語字幕
- 監看資料夾新影片並自動處理
- 提供桌面 GUI
