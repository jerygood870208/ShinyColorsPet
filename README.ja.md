# ShinyColorsPet

[繁體中文](README.md) | [日本語](README.ja.md) | [English](README.en.md)

ShinyColorsPet は、『アイドルマスター シャイニーカラーズ』をテーマにした非公式の
Windows デスクトップコンパニオンです。Spine 3.6 のデスクトップキャラクター表示に、
キャラクターチャット、長期記憶、親密度、音声、衣装管理を統合しています。

このリポジトリに含まれるのは、プログラム、審査済み UI 素材、キャラクタープロンプト、
音声参照データです。キャラクターの Spine モデルは含まれません。互換アセットは正当な
提供元から各自で入手し、アプリからインポートしてください。

## 特長

- 透明表示、ドラッグ、クリック、視線追従、意味ベースのアクション、表情、リップシンクに対応する
  **Spine 3.6 デスクトップキャラクター**。
- キャラクターごとの独立プロセスによる安定した複数キャラクター実行。
- Spine アセット検査、ユニット／キャラクター別表示、衣装と既定衣装の管理。
- OpenAI 互換 API、または明示的な同意が必要な実験的 `openai-oauth` プロキシによるチャット。
- キャラクター別の会話履歴、親密度、関係概要、長期記憶、Persona、`souls/` の内蔵人格。
  プロデューサー情報を設定できますが、名前はチャットプロンプトへ送信されません。
- ワンクリックで導入できるローカル Irodori-TTS v4.1／OpenAI 互換 TTS、ローカル
  `faster-whisper-large-v3`／OpenAI 互換 ASR。

## 主な機能

| 分類 | 機能 |
|---|---|
| デスクトップキャラクター | 複数起動、表示／非表示、最前面、拡大縮小、ドラッグ、クリック透過 |
| 動作と外観 | アクション、表情、視線、待機／ランダム動作、衣装、描画設定 |
| モデルとアセット | `dresses.json` フォルダーまたは単体 Spine 3.6 セットの取り込みと検証 |
| チャットと AI | キャラクター別チャット、OpenAI 互換 LLM、Persona、プロデューサー情報、画面コンテキスト |
| 関係データ | 親密度、関係概要、長期記憶、履歴、記憶アルバム、統計 |
| 音声 | Irodori-TTS 日本語音声、キャラクター参照音声、マイク入力、Whisper 音声認識 |
| データ管理 | バックアップ／復元、設定保存、アクティビティログ、システムトレイ |

## キャラクターモデルの追加

1. Spine 3.6 モデルを用意します。一括取り込みには `dresses.json`、単体セットには
   `data.json` と `data.atlas` が必要です。
2. **モデルとアセット** で、ダウンロードして展開したフォルダーを選択します。
3. **キャラクターモデルを更新** を実行します。検証済みアセットは
   `%LOCALAPPDATA%/ShinyColorsPet/models/` にコピーされ、manifest は `manifests/` に保存されます。
4. 再スキャン後、**ユニット → キャラクター** から起動できます。

## ソースから実行・ビルド

Windows 10/11 64-bit、Python 3.10 64-bit、Qt WebEngine／OpenGL を利用できる環境が必要です。

```powershell
git clone https://github.com/jerygood870208/ShinyColorsPet.git
cd ShinyColorsPet
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

ポータブル版の作成と検証：

```powershell
.\.venv\Scripts\python.exe packaging\freeze.py build_exe
.\.venv\Scripts\python.exe tools\validate_catalog.py data\catalog.json
.\.venv\Scripts\python.exe tools\validate_release_assets.py
.\.venv\Scripts\python.exe tools\verify_frozen_build.py build\ShinyColorsPet
```

成果物は `build/ShinyColorsPet/` に生成されます。配布時は `ShinyColorsPet.exe` だけでなく、
フォルダー全体を保持してください。

### ローカル Irodori-TTS

**TTS 設定**で **内蔵 Irodori-TTS v4.1** を選択すると、隔離環境を作成し、公式の
[Irodori-TTS](https://github.com/Aratako/Irodori-TTS) と
[Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server) をワンクリックで導入できます。
Python 3.10 以降、Git for Windows、対応する NVIDIA GPU、約 9 GB の空き容量が必要です。
WAV 以外の参照音声を使う場合は、システムの `PATH` から FFmpeg を利用できる必要があります。
Runtime とモデルは `%LOCALAPPDATA%/ShinyColorsPet/irodori-runtime/` に保存され、サービスは
`127.0.0.1:8088` のみで待ち受けます。

## 言語対応状況

繁体字中国語、簡体字中国語、日本語、英語に完全対応しています。翻訳カタログは
`shiny_pet/locales/` にあり、ナビゲーション、ページ、フォーム、ヒント、チャット操作、動的な状態表示に
適用されます。言語の変更は再起動後に反映されます。

## オープンソースコミュニティへの謝辞

- [BANDORI-PET-REV](https://github.com/HELPMEEADICE/BANDORI-PET-REV)：デスクトップペット、
  プロセス分離、設定保存、SD キャラクターモードの設計を参考にしました。
- [ShinyColorsDB](https://github.com/ShinyColorsDB)／
  [shinycolors.moe](https://shinycolors.moe/)：キャラクターデータ、UI 素材、Spine 表示研究の基礎。
- [Irodori-TTS](https://github.com/Aratako/Irodori-TTS)、
  [Irodori-TTS-Server](https://github.com/Aratako/Irodori-TTS-Server)、
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper)：ローカル音声機能を支えています。
- [Spine Runtimes](https://github.com/EsotericSoftware/spine-runtimes)、Python、Qt for Python、
  cx_Freeze、Pillow、PyYAML、NumPy、python-sounddevice、libsndfile、および関連する
  オープンソースプロジェクトと貢献者に感謝します。

## ライセンスと権利

別途明記されたものを除き、本プロジェクトが作成したコードおよび GPL 互換コードは
[GPL-3.0-only](LICENSE) で提供されます。GPL は第三者の商標、キャラクター、画像、音声、
モデル、Spine Runtime に対する権利を付与するものではありません。

`vendor/spine-runtime-3.6/` は GPL の対象外で、同梱の
[Spine Runtimes Software License](vendor/spine-runtime-3.6/LICENSE) が適用されます。
ソースまたはバイナリを再配布する場合は同ライセンスと条項を添付し、開発・配布に必要な
Spine ライセンスを保有していることを確認してください。詳細は
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。

『THE IDOLM@STER SHINY COLORS』の名称、キャラクター、画像、音声、モデル、商標、その他の
関連素材の権利は、BANDAI NAMCO Entertainment Inc. および各権利者に帰属します。
本プロジェクトは非公式のファンプロジェクトであり、各権利者との提携、後援、承認関係はありません。
