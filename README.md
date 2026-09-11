# ShinyColorsPet

[繁體中文](README.md) | [日本語](README.ja.md) | [English](README.en.md)

ShinyColorsPet 是一款以《偶像大師 閃耀色彩》為主題的非官方 Windows 桌面陪伴程式。
它使用 Spine 3.6 顯示桌面角色，並把角色聊天、長期記憶、好感度、語音與服裝管理整合在
同一個本機應用程式中。

本儲存庫只提供程式、經審核的介面資源、角色提示與語音參考；不包含角色 Spine 模型。
使用者必須自行從合法來源取得相容資產並匯入。

## 專案特色

- **Spine 3.6 桌面角色**：透明背景、拖曳、點擊互動、視線追蹤、語意動作、表情與嘴型同步。
- **多角色隔離執行**：每個桌寵由獨立程序管理；單一角色異常不會直接拖垮管理介面。
- **角色與服裝管理**：自動檢查 Spine 資產，依團體與人物瀏覽，並可設定每位角色的預設服裝。
- **角色聊天**：支援 OpenAI 相容 API，以及需由使用者明確同意的實驗性
  `openai-oauth` 第三方代理。
- **關係與記憶**：每位角色使用獨立聊天記錄、好感度、關係摘要、長期記憶、Persona 與
  `souls/` 內建人格；可設定製作人資料，但姓名不會送入聊天提示。
- **語音互動**：支援一鍵安裝的本機 Irodori-TTS v4.1／OpenAI 相容 TTS，以及本機
  `faster-whisper-large-v3`／OpenAI 相容語音辨識。

## 主要功能

| 類別 | 功能 |
|---|---|
| 桌面角色 | 啟動或停止多個角色、顯示／隱藏、置頂、縮放、拖曳及滑鼠穿透 |
| 動作與外觀 | 動作、表情、注視、待機／隨機動作、服裝與渲染設定 |
| 模型與資產 | 匯入 `dresses.json` 資料夾或單一 Spine 3.6 資產組，檢查並集中保存 manifest |
| 聊天與 AI | 角色專屬聊天室、OpenAI 相容 LLM、Persona、製作人資料與畫面情境 |
| 關係資料 | 好感度、關係摘要、長期記憶、聊天記錄、記憶相簿與統計 |
| 語音 | Irodori-TTS 日文語音、角色參考聲音、麥克風輸入與 Whisper 語音辨識 |
| 資料管理 | 本機資料備份／還原、設定保存、活動記錄與系統匣控制 |

## 匯入角色模型

1. 準備 Spine 3.6 模型。批次匯入資料夾應包含 `dresses.json`；單一資產組應直接包含
   `data.json` 與 `data.atlas`。
2. 開啟 **模型與資產**，選擇下載並解壓縮後的資料夾。
3. 選擇 **更新人物模型**。程式會檢查完整性並複製至：

   ```text
   %LOCALAPPDATA%/ShinyColorsPet/models/
   ```

4. 產生的 manifest 會存放於 `%LOCALAPPDATA%/ShinyColorsPet/manifests/`。匯入完成後，模型會
   立即重新掃描並顯示於 **團體 → 人物**。

## 自行執行與建置

### 環境需求

- Windows 10 或 Windows 11（64 位元）
- Python 3.10（64 位元）
- 可正常使用 Qt WebEngine／OpenGL 的顯示環境
- 建置與首次安裝相依套件時需要網路

### 從原始碼執行

```powershell
git clone https://github.com/jerygood870208/ShinyColorsPet.git
cd ShinyColorsPet
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

### 建立可攜式 Windows 版本

```powershell
.\.venv\Scripts\python.exe packaging\freeze.py build_exe
.\.venv\Scripts\python.exe tools\validate_catalog.py data\catalog.json
.\.venv\Scripts\python.exe tools\validate_release_assets.py
.\.venv\Scripts\python.exe tools\verify_frozen_build.py build\ShinyColorsPet
```

建置結果位於 `build/ShinyColorsPet/`。發布時必須保留整個資料夾，不能只複製
`ShinyColorsPet.exe`。`souls/` 與 `audio_reference/` 會整個納入成品；發布資產及最小 Spine
Runtime 則受 `packaging/` 內的審核清單控制。

### 本機 Irodori-TTS

在 **TTS 設定**選擇 **內建 Irodori-TTS v4.1**，即可一鍵建立隔離環境並安裝官方
[Irodori-TTS](https://github.com/Aratako/Irodori-TTS) 與
[Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server)。本機模式需要 Python
3.10 以上、Git for Windows、相容的 NVIDIA GPU 與約 9 GB 可用空間；非 WAV 參考音訊另需
系統 `PATH` 中可用的 FFmpeg。Runtime 與模型會存放於
`%LOCALAPPDATA%/ShinyColorsPet/irodori-runtime/`，不會寫入專案目錄；服務只監聽
`127.0.0.1:8088`。詳細流程見 [本機 Irodori-TTS 說明](docs/irodori-local-runtime.md)。

## 語言支援狀態

程式完整支援繁體中文、簡體中文、日文與英文。語系檔位於 `shiny_pet/locales/`；導覽、頁面、
表單、提示、聊天室控制及動態狀態均會依所選語言顯示，重新啟動後套用語言變更。

## 文件

- [應用程式原始碼導覽](docs/application-structure.md)
- [資料與資產架構](docs/architecture/data-and-assets.md)
- [本機 Irodori-TTS](docs/irodori-local-runtime.md)
- [外部 openai-oauth 整合](docs/integrations/openai-oauth.md)
- [第三方聲明](THIRD_PARTY_NOTICES.md)

## 感謝開源社群

- [BANDORI-PET-REV](https://github.com/HELPMEEADICE/BANDORI-PET-REV)：提供桌寵架構、程序隔離、
  設定保存與 Q 版角色模式的重要參考；衍生程式碼依 GPL-3.0 條款使用。
- [ShinyColorsDB](https://github.com/ShinyColorsDB) 與
  [shinycolors.moe](https://shinycolors.moe/)：提供角色資料、介面資源與 Spine 顯示研究的重要基礎。
- [Spine Runtimes](https://github.com/EsotericSoftware/spine-runtimes)：提供 Spine WebGL Runtime。
- [Python](https://www.python.org/)、[Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)、
  [cx_Freeze](https://github.com/marcelotduarte/cx_Freeze)、[Pillow](https://python-pillow.org/)、
  [PyYAML](https://pyyaml.org/)、[NumPy](https://numpy.org/)、
  [python-sounddevice](https://python-sounddevice.readthedocs.io/) 與
  [libsndfile](https://libsndfile.github.io/libsndfile/)：構成桌面介面、建置、影像與音訊基礎。
- [Irodori-TTS](https://github.com/Aratako/Irodori-TTS)、
  [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) 與
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper)：提供本機語音合成與語音辨識能力。

也感謝所有回報問題、測試、翻譯與維護相依套件的貢獻者。

## 授權與權利聲明

### GPL-3.0-only 範圍

除另有明確標示者外，本專案自行撰寫及由 GPL 相容來源改作的程式碼，以
[GNU General Public License v3.0 only](LICENSE) 發布。散布修改版或包含 GPL 程式碼的版本時，
必須依 GPL-3.0 提供相應原始碼、保留授權與著作權聲明，並以相同授權提供衍生作品。

GPL 只涵蓋有權以 GPL 發布的程式碼，不會授予第三方商標、角色、圖像、音訊、模型或 Spine
Runtime 的任何額外權利。

### Spine Runtime

`vendor/spine-runtime-3.6/` 不是 GPL 內容，而是適用 Esoteric Software 的
[Spine Runtimes Software License](vendor/spine-runtime-3.6/LICENSE)。本專案只打包實際使用的
Spine WebGL 3.6 檔案及其聲明。使用、修改或散布包含 Spine Runtime 的程式，必須遵守該授權；
其授權條款要求原始碼及二進位再散布均附帶該授權與條款，開發或散布應用程式時亦應確認自己
具有所需的 Spine 授權。詳情見 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

### 作品素材與商標

《THE IDOLM@STER SHINY COLORS》名稱、角色、圖像、音訊、模型、商標及其他相關素材之權利，
均歸 BANDAI NAMCO Entertainment Inc. 與各別權利人所有。這些內容不因收錄於本專案或其
發布包而改以 GPL 授權。

ShinyColorsPet 是非官方粉絲專案，與 BANDAI NAMCO Entertainment Inc.、Esoteric Software
或其他權利人沒有隸屬、贊助或背書關係。
