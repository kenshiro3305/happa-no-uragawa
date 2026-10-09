"""アクセストークンを60日先へ延長する。

長期トークンは60日で失効し、失効後は延長できない（取り直しになる）。
延長とSecretsへの書き戻しが成功した場合に有効期限が更新される。

トークンは標準出力に出さない。--out で指定したファイルにだけ書き、
ワークフロー側が `gh secret set ... < file` で読み取ってSecretsを更新する。

  python scripts/refresh_token.py --out new_token.txt
"""
import argparse
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


def die(msg):
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"エラー: {msg}")
    sys.exit(1)


def api_error_details(error):
    """応答本文をログに流さず、数値のエラー識別子だけ返す。"""
    details = [f"HTTP {error.code}"]
    try:
        response = json.loads(error.read().decode("utf-8"))
    except (ValueError, UnicodeError, OSError):
        return "、".join(details)
    if not isinstance(response, dict) or not isinstance(response.get("error"), dict):
        return "、".join(details)
    for key in ("code", "error_subcode"):
        value = response["error"].get(key)
        if type(value) is int and 0 <= value <= 2147483647:
            details.append(f"{key}={value}")
    return "、".join(details)


def save_token(out, token):
    """制限した権限の一時ファイルを置換し、途中までの値を残さない。"""
    destination = Path(out)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".ig-token-", dir=destination.parent)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(token)
        os.replace(temporary, destination)
    except OSError:
        die("延長後のトークンを保存できませんでした。出力先を確認してください。")
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Instagramトークンを延長してファイルへ保存する")
    parser.add_argument("--out", required=True, help="延長後のトークンの保存先")
    args = parser.parse_args(argv)

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        die("IG_ACCESS_TOKEN が未設定です")

    q = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": token})
    url = f"https://graph.instagram.com/refresh_access_token?{q}"

    try:
        with urllib.request.urlopen(url, context=ssl.create_default_context(), timeout=60) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        die("延長に失敗しました（" + api_error_details(e) + "）。すでに失効している場合は取り直しが必要です。")
    except (urllib.error.URLError, OSError):
        die("トークン延長の通信に失敗しました。実行ログの認証情報を表示せずに停止しました。")
    except (ValueError, UnicodeError):
        die("トークン延長APIの応答を解析できませんでした。応答本文は表示しません。")

    if not isinstance(res, dict):
        die("トークン延長APIから想定外の応答がありました。応答本文は表示しません。")
    new = res.get("access_token")
    expires = res.get("expires_in")
    if (not isinstance(new, str) or not new or any(char.isspace() or ord(char) < 32 for char in new)
            or type(expires) is not int or expires <= 0):
        die("トークン延長APIのトークンまたは有効期間が不正です。応答本文は表示しません。")
    save_token(args.out, new)  # 改行を入れない（gh secret set がそのまま読む）
    print(f"延長しました。有効期間 約{expires // 86400}日。トークンは指定ファイルに保存しました。")


if __name__ == "__main__":
    main()
