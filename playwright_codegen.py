#!/usr/bin/env python3
"""
Playwrightのコードジェネレータ
ブラウザでの操作を記録し、自動的にPythonコードを生成します
"""

import subprocess

def run_codegen():
    """Playwrightのコードジェネレータを実行する"""
    url = input("記録を開始するURLを入力してください（例: https://example.com）: ")
    output_file = input("生成されたコードの保存先ファイル名を入力してください（例: generated_code.py）: ")
    command = f"playwright codegen {url} --target python-async -o {output_file}"

    
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
