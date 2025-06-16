import os

# ユーザーデータディレクトリのパス
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
user_data_dir = os.path.join(script_dir, "user_data")

# ブラウザとコンテキスト共通の設定
browser_context_options = {
    # ブラウザ起動のオプション
    "headless": False,  # ヘッドレスモードを無効化（ブラウザUIを表示）
    "slow_mo": 100,     # アクションの間に遅延を追加（ミリ秒）
    "devtools": True,   # DevToolsを開いた状態で起動
    
    # コンテキスト設定
    "viewport": {
        "width": 1920, 
        "height": 1080
    },
    # "record_video_dir": "videos/",
    # "record_har_path": "logs/network.har",
    "ignore_https_errors": True,  # HTTPSエラーを無視
    "locale": "ja-JP",  # ロケールを日本語に設定
    "accept_downloads": True,  # ダウンロードを許可
    "bypass_csp": True,      # コンテンツセキュリティポリシーをバイパス
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
