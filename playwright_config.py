import os

# ユーザーデータディレクトリのパス
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
user_data_dir = os.path.join(script_dir, "user_data")


launch_options = {
    "headless": False,
    "slow_mo": 200,
    "devtools": False,
}


context_options = {
    "viewport": {"width": 1920, "height": 1080},
    "ignore_https_errors": True,
    "locale": "ja-JP",
    "accept_downloads": True,
    "bypass_csp": True,
}


# タイムアウト設定（ミリ秒）
timeouts = {
    "timeout": 60000,  # 全体のタイムアウト - 60秒に増加
    "navigation_timeout": 60000,  # ナビゲーションのタイムアウト - 60秒に増加
    "page_load_timeout": 60000,  # ページロードのタイムアウト - 60秒に増加
    "network_idle_timeout": 5000,  # ネットワークアイドル待機時間 - 5秒
}

# スクリーンショット設定
screenshot_options = {
    "full_page": True,
    "type": "png",
    "timeout": 30000,  # スクリーンショット取得のタイムアウト - 30秒
    "omit_background": False,  # 背景を含める
    "quality": 100,  # PNG品質（0-100）
}

# トレース設定
trace_options = {
    "screenshots": True,
    "snapshots": True,
    "sources": True,
}
