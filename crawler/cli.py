"""
コマンドライン引数の処理を行うモジュール
"""

import argparse
import os
import sys


def parse_args():
    """
    コマンドライン引数を解析する

    Returns:
        解析された引数オブジェクト
    """
    parser = argparse.ArgumentParser(
        description="Crawler with Snapshot - クローリングと同時に画面キャプチャも取るWebクローラー"
    )
    parser.add_argument("--resume", type=str, metavar="DIR", help="Resume crawl")
    parser.add_argument("--start-depth", type=int, metavar="N", help="Start crawling from specified depth (used with --resume)")
    parser.add_argument("--retry", type=str, metavar="DIR", help="Retry ERROR rows")
    parser.add_argument(
        "--domain-replace",
        type=str,
        metavar="CSV",
        help="Run domain replacement crawl on existing CSV",
    )
    return parser.parse_args()


def validate_args(args):
    """
    コマンドライン引数の検証を行う

    Args:
        args: 解析された引数オブジェクト

    Returns:
        検証結果: True (問題なし) または False (問題あり)
    """
    # domain-replace引数の検証
    if args.domain_replace and not os.path.exists(args.domain_replace):
        print(f"Error: CSVファイルが見つかりません: {args.domain_replace}")
        return False

    # retry引数の検証
    if args.retry and not os.path.isdir(args.retry):
        print(f"Error: ディレクトリが見つかりません: {args.retry}")
        return False

    # resume引数の検証
    if args.resume and not os.path.isdir(args.resume):
        print(f"Error: ディレクトリが見つかりません: {args.resume}")
        return False

    # start-depth引数の検証（resume指定時に必須）
    if args.resume and args.start_depth is None:
        print("Error: --resume オプション使用時は --start-depth の指定が必須です")
        return False

    return True
