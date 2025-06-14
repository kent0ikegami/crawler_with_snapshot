#!/usr/bin/env python3
"""
Playwrightのコードジェネレータ
ブラウザでの操作を記録し、自動的にPythonコードを生成します
"""

import subprocess
import sys
import json
import playwright_config

def run_codegen():
    """Playwrightのコードジェネレータを実行する"""
    url = input("記録を開始するURLを入力してください（例: https://example.com）: ")
    output_file = input("生成されたコードの保存先ファイル名を入力してください（例: generated_code.py）: ")
    
    # playwright_configからブラウザオプションを取得
    browser_args = []
    
    # headless設定を適用
    if not playwright_config.browser_options.get("headless", False):
        browser_args.append("--headed")
    
    # devtools設定を適用
    if playwright_config.browser_options.get("devtools", False):
        browser_args.append("--device-scale-factor=1")
    
    # viewport設定を適用
    if "viewport" in playwright_config.context_options:
        viewport = playwright_config.context_options["viewport"]
        browser_args.append(f"--viewport-size={viewport['width']}x{viewport['height']}")
    
    # slow_mo設定を適用
    if "slow_mo" in playwright_config.browser_options:
        browser_args.append(f"--timeout={playwright_config.browser_options['slow_mo']}")
    
    # ブラウザ引数を文字列に変換
    browser_args_str = " ".join(browser_args)
    
    # OSに応じたコマンドを構築
    command = f"playwright codegen {browser_args_str} {url} --target python-async -o {output_file}"
    
    print(f"コードジェネレータを起動しています: {command}")
    print("ブラウザでの操作を記録します。完了したらコードジェネレータウィンドウを閉じてください。")
    
    try:
        subprocess.run(command, shell=True)
        print(f"コードが {output_file} に生成されました。")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        print("\nPlaywrightのインストールを確認してください:")
        print("pip install playwright")
        print("playwright install")

if __name__ == "__main__":
    run_codegen()
