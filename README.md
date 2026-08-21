# Autosubtitle

Autosubtitle 是可部署在一般電腦、NVIDIA GPU 工作站、GB10 或 NAS 的內網字幕服務。它能從瀏覽器上傳影片、處理伺服器既有影片，或持續監控資料夾，自動產生同名 `.srt` 外掛字幕。

## 主要功能

- Web 管理介面與命令列模式
- 上傳、指定路徑及資料夾監控三種工作來源
- Whisper 語音辨識，支援 CPU 與 CUDA
- Google、Ollama、OpenAI-compatible API 翻譯
- 原文、翻譯或雙語字幕，預設目標語言為繁體中文 `zh-TW`
- SQLite 工作佇列與全域設定，服務重啟後仍會保留
- 完成後從網頁下載 `.srt`，或直接輸出到原影片旁
- 支援 `.mp4`、`.mkv`、`.mov`、`.avi`、`.m4v`、`.webm`

## 本機啟動

需要 Python 3.11 以上及 `ffmpeg`：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py web
```

Windows PowerShell 啟用虛擬環境：

```powershell
.venv\Scripts\Activate.ps1
```

啟動後開啟 `http://localhost:8000`。Whisper 模型會在第一個辨識工作開始時下載。

如果 pip 顯示 `pypi.org/simple` 缺少 URL scheme，可修正套件來源：

```bash
python -m pip config set global.index-url https://pypi.org/simple
```

## Web 使用方式

### 上傳影片

在首頁選擇影片並排入工作。完成後，工作列表會出現「下載 SRT」；影片和字幕保存在 `state/uploads`。

### 指定伺服器影片

輸入服務主機或容器可存取的完整路徑。Docker 中主機影片目錄掛載為 `/data`，例如主機的 `lesson/demo.mp4` 在網頁應填 `/data/lesson/demo.mp4`。

### 監控資料夾

輸入 `/data` 或 `/data/incoming` 並選擇是否包含子資料夾。新影片的大小與修改時間保持穩定後才會排入，避免處理尚未複製完成的檔案；字幕會寫在原影片旁邊。

可透過環境變數調整掃描行為：

```dotenv
AUTOSUB_SCAN_INTERVAL=10
AUTOSUB_STABLE_SECONDS=30
AUTOSUB_OVERWRITE=false
```

若已有同名字幕，預設會略過。`movie.mp4` 和 `movie.mkv` 會產生相同的 `movie.srt`，因此系統會阻止輸出路徑衝突。

## Docker 部署

建立環境設定和影片資料夾：

```bash
cp .env.example .env
mkdir -p videos
```

CPU：

```bash
docker compose --profile cpu up --build -d
```

NVIDIA GPU 或相容的 GB10 環境：

```bash
docker compose --profile gpu up --build -d
```

開啟 `http://主機IP:8000`。`.env` 的 `AUTOSUB_MEDIA_DIR` 會掛載為容器內的 `/data`。

GPU 映像預設使用 `nvcr.io/nvidia/pytorch:25.11-py3`，需要其他 CUDA/PyTorch 組合時可設定：

```dotenv
AUTOSUB_GPU_BASE_IMAGE=相容的映像名稱
```

## QNAP TS-877

TS-877 使用 `linux/amd64` CPU 映像。QNAP Container Station 若不接受 Docker 29 匯出的 OCI archive，請使用 legacy Docker archive：

```text
autosubtitle-qnap-ts877-cpu-amd64-v2-qnap-legacy.tar
```

TAR 約 2.4 GB，已被 `.gitignore` 排除，不會上傳到 GitHub；請另外複製到 NAS。匯入後，在 Container Station 的「應用程式」使用 `compose.qnap.yaml` 建立服務。

目前範例使用以下共享資料夾：

```yaml
volumes:
  - /share/AutosubtitleVideo:/data
  - /share/Container/autosubtitle/state:/state
  - /share/Container/autosubtitle/cache:/root/.cache/whisper
```

部署步驟：

1. 在 File Station 建立 `AutosubtitleVideo`，以及 `Container/autosubtitle/state`、`Container/autosubtitle/cache`。
2. 在 Container Station 的「映像檔」匯入含 `qnap-legacy` 的 TAR。
3. 在「應用程式」建立專案並貼入 `compose.qnap.yaml`。
4. 確認連接埠轉送為 `主機 8000 -> 容器 8000/TCP`。
5. 開啟 `http://QNAP-IP:8000`，監控路徑填 `/data`；不要填 NAS 主機路徑 `/share/AutosubtitleVideo`。

第一次辨識需要網路下載 Whisper 模型。模型快取和 SQLite 狀態均已掛載到 NAS，重建容器後仍會保留。

## 辨識設定

Web 首頁可修改模型、來源語言、裝置、精度與 beam size。環境變數預設值如下：

```dotenv
AUTOSUB_DEVICE=auto
AUTOSUB_COMPUTE_TYPE=auto
AUTOSUB_MODEL=base
AUTOSUB_LANGUAGE=
AUTOSUB_BEAM_SIZE=5
```

`auto` 在 PyTorch 可使用 CUDA 時選擇 GPU 與 FP16，否則使用 CPU 與 FP32。較大的模型通常更準，但需要更多記憶體與處理時間。

## 翻譯設定

Google 翻譯適合試用，但依賴外部網路服務：

```dotenv
AUTOSUB_TRANSLATE=true
AUTOSUB_TRANSLATION_PROVIDER=google
AUTOSUB_TARGET_LANGUAGE=zh-TW
AUTOSUB_BILINGUAL=false
```

Ollama 本地模型：

```dotenv
AUTOSUB_TRANSLATE=true
AUTOSUB_TRANSLATION_PROVIDER=ollama
AUTOSUB_LLM_ENDPOINT=http://host.docker.internal:11434
AUTOSUB_LLM_MODEL=gemma3:12b
AUTOSUB_TARGET_LANGUAGE=zh-TW
```

OpenAI-compatible API：

```dotenv
AUTOSUB_TRANSLATE=true
AUTOSUB_TRANSLATION_PROVIDER=openai
AUTOSUB_LLM_ENDPOINT=https://example.com/v1/chat/completions
AUTOSUB_LLM_MODEL=your-model
AUTOSUB_LLM_API_KEY=your-secret
```

Linux 容器若無法解析 `host.docker.internal`，請改用 Ollama 主機的內網 IP，或把兩個服務加入同一個 Compose 網路。LLM 翻譯會驗證回傳字幕數量，避免翻譯漏句造成時間軸錯位。

## CLI 模式

```bash
python main.py videos --recursive --model small
python main.py videos --translate --target-language zh-TW --bilingual
python main.py videos --translate --translation-provider ollama \
  --llm-endpoint http://localhost:11434 --llm-model gemma3:12b
```

預設可存取路徑只有 `state/uploads`。Web 服務需要存取其他主機資料夾時，可設定多個允許根目錄；Linux 使用冒號，Windows 使用分號分隔：

```bash
AUTOSUB_ALLOWED_ROOTS=/mnt/videos:/mnt/shared python main.py web
```

## 安全與維運

Web 介面目前適合可信任的內網。對辦公室或校園多人開放前，應加入登入驗證與 HTTPS 反向代理，不要直接暴露到網際網路，也不要將 `AUTOSUB_ALLOWED_ROOTS` 設為 `/`。

目前 Web 服務應只啟動一個程序，因為模型 Worker 與掃描器位於同一程序。需要多 GPU、多主機或高併發時，建議將 Worker 拆成獨立服務並使用 Redis 工作佇列。

## 測試

```bash
python -m unittest discover -s tests -v
node --check autosubtitle/static/app.js
```
