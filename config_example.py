LOGIN_URL = "https://example.com/login"
USERNAME = "your_username"
PASSWORD = "your_password"
USERNAME_SELECTOR = "#username"
PASSWORD_SELECTOR = "#password"
SUBMIT_SELECTOR = "button[type=submit]"
LOGIN_SUCCESS_URL_PATTERN = "**/dashboard"
LOGIN_WAIT_SELECTOR = "#welcomeMessage"
START_URLS = ["https://example.com/"]
MAX_DEPTH = 1
USE_USER_DATA = True
USE_USER_DATA_AND_LOGIN = False
ALLOWED_DOMAINS = [
    "example.com",
]
SKIP_LINK_KEYWORDS = []
SKIP_URL_PATTERNS = []
WAIT_FOR_TEXT_TO_DISAPPEAR = ""
