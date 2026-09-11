# BANDORI-PET-REV 模組來源與調整

參考：BANDORI-PET-REV `745c6936a7e18779394b2f622577a0371b85c4b7`，GPL-3.0。
本專案既有 GPLv3 LICENSE 保持不變。

| 來源模組 | 本專案實作 | 調整 |
|---|---|---|
| main.py、pet_process.py、process_utils.py | process/manager.py、worker.py | 沿用 QProcess 隔離與父死亡退出行為；縮為父子管線 IPC，無 AI／聊天依賴 |
| config_manager.py | settings/store.py、legacy/settings.py | 保留 backup、原子替換策略；新 schema、純函式 migration、單寫入者 |
| tray_utils.py、main.py 托盤 | app/desktop_panel.py | QWidget-owned menu、無托盤 fallback；使用 Qt 標準圖示，不複製品牌素材 |
| pixel_pet_widget.py | renderer/chibi.py、window/chibi_window.py | 產品名稱改為「Q版模式」；沿用 sprite 格式、三拍幀時序與 alpha 命中；輸入和視窗移至 controller；不搬入自主散步 |

未複製參考專案圖片、角色資料、Live2D／Lua runtime 或設定中的私人資料。
Spine runtime／角色資產仍使用使用者外部路徑，未新增至發行資產。
