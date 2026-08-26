"""アクセストークンを60日先へ延長する。

長期トークンは60日で失効し、失効後は延長できない（取り直しになる）。
毎日実行して常に60日先へ押し出しておけば、期限切れで止まることがなくなる。

トークンは標準出力に出さない。--out で指定したファイルにだけ書き、
ワークフロー側が `gh secret set ... < file` で読み取ってSecretsを更新する。

  python scripts/refresh_token.py --out new_token.txt
"""
import json, os, ssl, sys, urllib.error, urllib.parse, urllib.request


def die(msg):
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"エラー: {msg}")
    sys.exit(1)


def main():
    argv = sys.argv[1:]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        die("IG_ACCESS_TOKEN が未設定です")

    q = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": token})
    url = f"https://graph.instagram.com/refresh_access_token?{q}"

    try:
        with urllib.request.urlopen(url, context=ssl.create_default_context(), timeout=60) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        die("延長に失敗しました。すでに失効している場合は取り直しが必要です。\n" + body)

    new = res.get("access_token")
    days = res.get("expires_in", 0) // 86400
    if not new:
        die(f"想定外の応答: {res}")

    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(new)          # 改行を入れない（gh secret set がそのまま読む）
        print(f"延長しました。有効期間 約{days}日。トークンは {out} に書き出しました。")
    else:
        print(f"延長しました。有効期間 約{days}日。")
        print("（--out を指定していないため、新トークンは保存していません）")


if __name__ == "__main__":
    main()
