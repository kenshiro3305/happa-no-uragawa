# 葉っぱの裏側 — Instagram自動投稿

出典つき植物雑学アカウント [@happa_no_uragawa](https://www.instagram.com/happa_no_uragawa/) の投稿を、GitHub Actionsから自動で公開する。

## 動き

```
月・水・金 08:00 JST に起動
  → schedule.json の未投稿を1件取り出す
  → production 環境の承認を待つ（承認者を設定した場合）
  → 承認されたらカルーセルとして投稿
  → 投稿済みフラグをコミットして戻す
```

トークンは毎日60日先へ延長されるので、期限切れで止まらない（`GH_PAT` を登録した場合）。

## なぜPublicリポジトリなのか

Instagram APIは**画像ファイルを受け取らない**。画像の**公開URL**を渡し、Meta側がそこへ取りに来る方式。

Publicリポジトリなら `raw.githubusercontent.com` がそのまま公開URLとして使えるため、Cloudinaryなどの画像ホスティングが不要になる。

- GitHub Secretsは、Publicリポジトリでも公開されない
- 副作用として、未投稿の画像とキャプションが事前に見える状態になる
- **Privateにすると画像URLが取得できず、投稿は必ず失敗する**

## 構成

| パス | 中身 |
|---|---|
| `posts/01`〜`08/` | 投稿1本ぶんのPNG 7枚（1080×1350、名前順が投稿順） |
| `posts/captions/` | 各投稿の本文とハッシュタグ |
| `schedule.json` | 予定時刻と投稿済みフラグ |
| `scripts/post_instagram.py` | 投稿本体 |
| `scripts/refresh_token.py` | トークン延長 |
| `.github/workflows/post.yml` | 投稿ワークフロー |
| `.github/workflows/refresh-token.yml` | 延長ワークフロー |

## セットアップ

```bash
cp .env.example .env.local   # 値を埋める（チャットに貼らないこと）
bash setup.sh                # GitHub Secrets へ登録
```

必要なSecrets

| 名前 | 必須 | 用途 |
|---|---|---|
| `IG_USER_ID` | ○ | Instagramのユーザー番号 |
| `IG_ACCESS_TOKEN` | ○ | アクセストークン |
| `GH_PAT` | 推奨 | トークン自動延長。**未設定だと60日後に無言で止まる** |

登録後、Settings → Environments → `production` を作り、Required reviewers に自分を追加すると承認制になる。スマホのGitHubアプリに通知が届き、タップで承認できる。

## 手動で1本出す

```
Actions →「Instagram 投稿」→ Run workflow → 番号に 01 を入力
```

**自動運転に入る前に、必ず1本は手動で出して表示を確認すること。** カルーセルの見え方と改行の入り方は、実際に投稿するまで確定しない。

## 新しい投稿を足すとき

画像7枚を `posts/NN/` に、本文を `posts/captions/NN.txt` に置き、`schedule.json` に行を追加する。画像の生成には別途 `slides.py`（台本JSON → PNG）を使う。

## 運用ルール

このアカウントの資産は「出典が正確であること」だけ。

- 孫引きしない。元論文の著者・掲載誌・年を確認してから使う
- 擬人化しない（「悲鳴」「助け合う」「聞く」は注釈を添える）
- 研究の限界を書く（被験者数、動物実験である旨）
- 健康効果を断言しない
- 迷ったら出さない

## 既知の制約

- GitHub Actionsのcronは混雑時に数十分遅れる。分単位の精度は出ない
- カルーセルは1枚目のアスペクト比に他が揃えられる（全て4:5で統一済み）
- API経由の投稿は24時間で100件まで
- Instagramのパスワードを変更するとトークンが失効する
