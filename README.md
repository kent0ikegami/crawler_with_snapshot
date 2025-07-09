# README

## setting 

```bash
pip install playwright requests beautifulsoup4
playwright install
cp config_example.py config.py 
python login.py
```

## do

```bash
python main.py

# 再開
python main.py --resume results/20250708_093000

# エラー行の再試行
python main.py --retry results/20250709_115006

# ドメイン置換クローリング（既存のCSVに対してドメインを変更してクロールを実行）
python main.py --domain-replace results/20250709_145122/result.csv
```

## other

```bash
python playwright_inspector.py
python playwright_codegen.py
```

## memo

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --no-first-run
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --no-first-run --user-data-dir="$HOME/Library/Application Support/Google/Chrome"
lsof -i :9222
http://127.0.0.1:9222/json/version
```
