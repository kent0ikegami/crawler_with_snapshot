# README


## setting 

```bash
pip install playwright requests beautifulsoup4
playwright install
cp config_example.py config.py 
python login_and_save_state.py
```

## do

```bash
python main.py
```

## other

```bash
python playwright_inspector.py
python playwright_codegen.py
```


## memo

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --no-first-run
# デスクトップに user-dateを設定
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --no-first-run --user-data-dir="$HOME/Library/Application Support/Google/Chrome"

lsof -i :9222

http://127.0.0.1:9222/json/version
```
