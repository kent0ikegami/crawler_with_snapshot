import os

# ユーザーデータディレクトリのパス
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
user_data_dir = os.path.join(script_dir, "user_data")


launch_options = {
    "headless": False,
    "slow_mo": 100,
    "devtools": True,
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
    "timeout": 30000,         # 全体のタイムアウト
    "navigation_timeout": 30000,  # ナビゲーションのタイムアウト
    "page_load_timeout": 30000,   # ページロードのタイムアウト 
}

# スクリーンショット設定
screenshot_options = {
    "full_page": True,
    "type": "png",
}

# トレース設定
trace_options = {
    "screenshots": True,
    "snapshots": True,
    "sources": True,
}
