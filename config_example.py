# config.py

# ログイン設定
LOGIN_URL = "https://example.com/login"
USERNAME = "your_username"
PASSWORD = "your_password"
USERNAME_SELECTOR = "#username"
PASSWORD_SELECTOR = "#password"
SUBMIT_SELECTOR = "button[type=submit]"
LOGIN_SUCCESS_URL_PATTERN = "**/dashboard"

# クロール対象
START_URLS = [
    "https://example.com/"
]

# クロールの最大深さ
MAX_DEPTH = 1

USE_LOGIN = False