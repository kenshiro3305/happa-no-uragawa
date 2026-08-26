#!/usr/bin/env bash
# .env.local に書いた値を GitHub Secrets に登録する。
# 値がこの端末とGitHubの外に出ないようにするための入り口。

set -uo pipefail

REPO="${REPO:-kenshiro3305/happa-no-uragawa}"
ENV_FILE=".env.local"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
ng()   { printf '  \033[31m✗\033[0m %s\n' "$1"; }

echo "============================================"
echo "  葉っぱの裏側 — Secrets 登録"
echo "  対象: $REPO"
echo "============================================"
echo

if ! command -v gh >/dev/null 2>&1; then
  ng "gh コマンドが見つかりません。GitHub CLI を入れてください。"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  ng "GitHub にログインしていません。 gh auth login を実行してください。"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  ng "$ENV_FILE がありません。"
  echo "     cp .env.example .env.local  してから値を入れてください。"
  exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

REQUIRED=(IG_USER_ID IG_ACCESS_TOKEN)
OPTIONAL=(GH_PAT)

echo "入力の確認"
missing=0
for name in "${REQUIRED[@]}"; do
  if [ -z "${!name:-}" ]; then ng "$name が空です"; missing=1; else ok "$name"; fi
done
[ "$missing" -eq 1 ] && { echo; ng "必須項目が未入力です。中止します。"; exit 1; }

if [ "${#IG_ACCESS_TOKEN}" -lt 50 ]; then
  warn "IG_ACCESS_TOKEN が短いようです（${#IG_ACCESS_TOKEN}文字）。コピー漏れがないか確認してください。"
fi
if [[ "$IG_USER_ID" =~ [^0-9] ]]; then
  warn "IG_USER_ID に数字以外が含まれています。ユーザーネームではなく数字のIDです。"
fi
if [ -z "${GH_PAT:-}" ]; then
  warn "GH_PAT が空です。トークンの自動延長が働かず、60日後に投稿が止まります。"
fi

echo
echo "Secrets を登録します"
for name in "${REQUIRED[@]}" "${OPTIONAL[@]}"; do
  value="${!name:-}"
  [ -z "$value" ] && continue
  if printf '%s' "$value" | gh secret set "$name" --repo "$REPO" >/dev/null 2>&1; then
    ok "$name を登録しました"
  else
    ng "$name の登録に失敗しました"
  fi
done

echo
echo "登録済みの一覧"
gh secret list --repo "$REPO" 2>/dev/null | sed 's/^/  /' || true

echo
echo "次にやること"
echo "  1. Settings → Environments → production を作り、"
echo "     Required reviewers に自分を追加する（承認制にする場合）"
echo "  2. Actions タブ →「Instagram 投稿」→ Run workflow で番号 01 を指定し、"
echo "     1本目を手動で出して表示を確認する"
echo
echo "  ★ 確認が済んだら .env.local は削除して構いません。"
