# Autosubtitle

自動掃描資料夾中的影片檔，並為每支影片產生同名的外掛字幕檔 (`.srt`)。

目前版本使用 OpenAI Whisper 與 PyTorch 做語音辨識，預設只產生原文字幕檔，不執行翻譯。

## 功能

- 掃描指定資料夾中的影片
- 持續監看新加入或更新的影片
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
- PyTorch（使用 GPU 時需安裝與 CUDA 相容的版本）

若使用 NVIDIA GB10／DGX Spark，請改看 [GB10 / DGX Spark 安裝指南](GB10_DGX_SPARK.md)。

## 安裝

先安裝 `ffmpeg`。Ubuntu／Debian：

```bash
sudo apt update
sudo apt install ffmpeg
```

建立 Python 虛擬環境並安裝相依套件：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

確認 Whisper 可使用的裝置：

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

## 使用方式

掃描 `videos` 資料夾，為所有影片產生字幕：

```bash
python3 main.py videos
```

程式預設使用 CUDA。沒有可用 CUDA GPU 時，請改用 CPU：

```bash
python3 main.py videos --device cpu --compute-type float32
```

指定辨識語言：

```bash
python3 main.py videos --model small --language zh
```

如需暫時啟用既有翻譯模組：

```bash
python3 main.py videos --translate
```

輸出雙語字幕：

```bash
python3 main.py videos --translate --bilingual
```

遞迴掃描並覆寫既有字幕：

```bash
python3 main.py videos --recursive --overwrite
```

## 監看資料夾

持續監看 `videos`，新影片寫入完成後自動產生字幕：

```bash
python3 main.py videos --watch
```

連同子資料夾一起監看：

```bash
python3 main.py videos --watch --recursive
```

監看模式預設每 2 秒掃描一次，影片大小與修改時間連續 10 秒不變才會開始處理，避免讀取尚未複製完成的檔案。可用 `--poll-interval` 與 `--stable-seconds` 調整。

離開終端後持續監看：

```bash
nohup .venv/bin/python main.py videos --watch --recursive \
  > autosubtitle.log 2>&1 &
```

查看日誌：

```bash
tail -f autosubtitle.log
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
- 加上 `--translate` 才會執行 LLM 翻譯模組
- 使用 `config.toml` 選擇 API 或本地模型
- `--config` 可載入其他設定檔
- `--target-language` 與 `--bilingual` 可覆寫設定檔
- 若加上 `--bilingual`，每個字幕區塊會先放原文，再放翻譯內容

### 翻譯模型設定

編輯 `config.toml`：

```toml
[translation]
mode = "local" # 可選 "api" 或 "local"
target_language = "zh-TW"
bilingual = false
batch_size = 20
timeout_seconds = 120

[translation.api]
model = "gpt-4o-mini"
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"

[translation.local]
model = "qwen3:8b"
base_url = "http://127.0.0.1:11434/v1"
api_key_env = ""
```

API 模式不會把金鑰寫入設定檔。先設定環境變數：

```bash
export OPENAI_API_KEY="你的金鑰"
python3 main.py videos --translate
```

本地模式支援提供 OpenAI-compatible API 的服務，例如 Ollama 或 vLLM。

## 後續可擴充

- 產生 `.vtt`
- 批次加上雙語字幕
- 提供桌面 GUI
