"""葉っぱの裏側 — Instagram カルーセル投稿

画像はこのリポジトリ内に置き、raw.githubusercontent.com の公開URLを
そのままInstagram APIに渡す。Instagram APIは画像ファイルを受け取らず
「公開URLを渡してMeta側が取りに来る」方式のため、この手が使える。
リポジトリがPublicである必要があるのはそのため（Cloudinaryは不要）。

環境変数:
  IG_USER_ID          Instagramのユーザー番号
  IG_ACCESS_TOKEN     アクセストークン
  GITHUB_REPOSITORY   owner/repo（Actionsが自動で入れる）
  GITHUB_REF_NAME     ブランチ名（既定 main）

  python scripts/post_instagram.py            # 予定時刻を過ぎた先頭1件
  python scripts/post_instagram.py --no 01    # 番号を指定
  python scripts/post_instagram.py --dry-run  # URL組み立てまでで停止
"""
import argparse, json, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEDULE = os.path.join(ROOT, "schedule.json")
POSTS = os.path.join(ROOT, "posts")
JST = timezone(timedelta(hours=9))
API_VERSION = os.environ.get("IG_API_VERSION", "v21.0")


def die(msg):
    print(f"::error::{msg}" if os.environ.get("GITHUB_ACTIONS") else f"エラー: {msg}")
    sys.exit(1)


def request(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        # トークンは絶対にログに出さない
        safe = url.split("?")[0]
        die(f"{safe} が HTTP {e.code} で失敗\n{detail}")


class IG:
    def __init__(self, uid, token):
        self.base = f"https://graph.instagram.com/{API_VERSION}"
        self.uid, self.token = uid, token

    def item(self, image_url):
        return request(f"{self.base}/{self.uid}/media",
                       {"image_url": image_url, "is_carousel_item": "true",
                        "access_token": self.token})["id"]

    def carousel(self, children, caption):
        return request(f"{self.base}/{self.uid}/media",
                       {"media_type": "CAROUSEL", "children": ",".join(children),
                        "caption": caption, "access_token": self.token})["id"]

    def wait(self, cid, tries=25, gap=4):
        """FINISHEDを待たずにpublishすると失敗する。"""
        for i in range(tries):
            q = urllib.parse.urlencode({"fields": "status_code", "access_token": self.token})
            code = request(f"{self.base}/{cid}?{q}").get("status_code")
            if code == "FINISHED":
                return
            if code == "ERROR":
                die(f"コンテナ {cid} の処理が失敗しました")
            print(f"  処理待ち {i+1}/{tries} … {code}")
            time.sleep(gap)
        die(f"コンテナ {cid} が時間内に完成しませんでした")

    def publish(self, cid):
        return request(f"{self.base}/{self.uid}/media_publish",
                       {"creation_id": cid, "access_token": self.token})


def raw_base():
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        die("GITHUB_REPOSITORY が未設定です（ローカル実行時は手動で指定してください）")
    ref = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{ref}"


def pick(schedule, forced, allow_posted=False):
    if forced:
        for e in schedule["予定"]:
            if e["番号"] == forced:
                if e["投稿済み"] and not allow_posted:
                    die(f"番号 {forced} は投稿済みです。再投稿は拒否しました（確認には --dry-run を使用）")
                return e
        die(f"番号 {forced} が schedule.json にありません")
    now = datetime.now(JST)
    for e in schedule["予定"]:
        if e["投稿済み"]:
            continue
        due = datetime.strptime(e["予定時刻"], "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        if due <= now:
            return e          # 1回の実行で1件だけ
    return None


def main():
    parser = argparse.ArgumentParser(description="Instagramカルーセル投稿")
    parser.add_argument("--no", help="schedule.jsonの投稿番号")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    dry, forced = args.dry_run, args.no
    if forced and (not forced.isascii() or not forced.isdecimal()):
        die("--no には数字の投稿番号だけを指定してください")

    uid = os.environ.get("IG_USER_ID", "").strip()
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not dry and (not uid or not token):
        missing = [name for name, value in (("IG_USER_ID", uid), ("IG_ACCESS_TOKEN", token)) if not value]
        die("必須Secretsが未設定: " + ", ".join(missing))

    with open(SCHEDULE, encoding="utf-8") as f:
        schedule = json.load(f)

    entry = pick(schedule, forced, allow_posted=dry)
    if entry is None:
        print("投稿予定はありません。")
        return
    no = entry["番号"]

    folder = os.path.join(POSTS, no)
    if not os.path.isdir(folder):
        die(f"posts/{no} がありません")
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
    if not files:
        die(f"posts/{no} にPNGがありません")
    if len(files) > 10:
        die(f"カルーセルは10枚まで（{len(files)}枚あります）")

    cap_path = os.path.join(POSTS, "captions", f"{no}.txt")
    if not os.path.exists(cap_path):
        die(f"キャプション posts/captions/{no}.txt がありません")
    caption = open(cap_path, encoding="utf-8").read().strip()

    urls = [f"{raw_base()}/posts/{no}/{urllib.parse.quote(f)}" for f in files]

    print(f"■ {no} を投稿します（{len(urls)}枚）")
    print(f"  1枚目: {urls[0]}")
    print(f"  冒頭  : {caption.splitlines()[0][:40]}…")

    if dry:
        print("\n--dry-run のため停止します。投稿はしていません。")
        for u in urls:
            print("  " + u)
        return

    ig = IG(uid, token)
    print("\n[1/3] 各画像のコンテナを作成")
    children = [ig.item(u) for u in urls]
    print(f"  {len(children)} 件")

    print("[2/3] カルーセルをまとめる")
    cid = ig.carousel(children, caption)
    ig.wait(cid)

    print("[3/3] 公開")
    res = ig.publish(cid)
    media_id = res.get("id", "")
    print(f"\n✅ 投稿しました media_id={media_id}")

    entry["投稿済み"] = True
    entry["実投稿時刻"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    entry["media_id"] = media_id
    with open(SCHEDULE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    print("schedule.json を更新しました。")


if __name__ == "__main__":
    main()
