# Autosubtitle

自動掃描資料夾中的影片檔，並為每支影片產生同名的外掛字幕檔 (`.srt`)。

目前版本使用 `faster-whisper` 做語音辨識，並可自動翻譯字幕內容。預設會翻譯成繁體中文。

## 功能

- 掃描指定資料夾中的影片
- 支援遞迴掃描子資料夾
- 為每支影片輸出同名 `.srt`
- 可指定 Whisper 模型大小
- 可指定語言，或交給模型自動判斷
- 預設將字幕翻譯成繁體中文
- 可指定翻譯成其他語言
- 可輸出雙語字幕
- 可選擇是否覆寫既有字幕檔

## 環境需求

- Python 3.11+
- `ffmpeg`

## 安裝

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

指定辨識語言，但仍翻譯成繁體中文：

```bash
python3 main.py videos --model small --language zh
```

翻譯成英文：

```bash
python3 main.py videos --target-language en
```

輸出雙語字幕：

```bash
python3 main.py videos --bilingual
```

只做辨識，不做翻譯：

```bash
python3 main.py videos --no-translate
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

預設情況下，`demo.srt` 內容會是翻譯後的繁體中文字幕。

## 翻譯說明

- 預設目標語言是 `zh-TW`
- 目前翻譯使用 Google Translate 介面，因此執行翻譯時需要網路
- 若加上 `--bilingual`，每個字幕區塊會先放原文，再放翻譯內容
- 若來源語言與目標語言相同，系統會直接保留原字幕文字

## 後續可擴充

- 產生 `.vtt`
- 批次加上雙語字幕
- 監看資料夾新影片並自動處理
- 提供桌面 GUI
