"""Actions の設定を検査する。値は表示せず、外部APIも呼ばない。"""
import argparse
import os
import sys

REQUIRED = {
    "post": ("IG_USER_ID", "IG_ACCESS_TOKEN"),
    "refresh": ("IG_ACCESS_TOKEN", "GH_PAT"),
}
MAIL_REQUIRED = ("DIGEST_TO", "SMTP_USER", "SMTP_PASS")


def inspect_config(purpose, env, dry_run=False):
    required = () if purpose == "post" and dry_run else REQUIRED[purpose]
    missing = [name for name in required if not env.get(name, "").strip()]
    mail_missing = [name for name in MAIL_REQUIRED if not env.get(name, "").strip()]
    reason = "必要な設定は揃っています（有効性は未検証）"
    if missing:
        reason = "必須Secretsが未設定: " + ", ".join(missing)
    elif purpose == "post" and dry_run:
        reason = "dry-run: 認証不要、Instagram APIへの通信なし"
    return {
        "ready": not missing,
        "missing": missing,
        "mail_ready": not mail_missing,
        "mail_missing": mail_missing,
        "reason": reason,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purpose", required=True, choices=REQUIRED)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = inspect_config(args.purpose, os.environ, args.dry_run)
    outputs = {
        "ready": str(config["ready"]).lower(),
        "missing": ", ".join(config["missing"]),
        "reason": config["reason"],
        "mail_ready": str(config["mail_ready"]).lower(),
        "mail_missing": ", ".join(config["mail_missing"]),
    }
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
            for name, value in outputs.items():
                file.write(f"{name}={value}\n")
    summary = ["## 自動投稿の設定確認", "", config["reason"], ""]
    if config["mail_missing"]:
        summary += [
            "メール通知も未設定: " + ", ".join(config["mail_missing"]),
            "この実行ではメールを送信できません。IssueとActionsログを確認してください。",
            "",
        ]
        print("::warning::メール通知のSecretsが未設定: " + ", ".join(config["mail_missing"]))
    summary += [
        "保存先: Settings → Secrets and variables → Actions → Repository secrets。",
        "延長ジョブはrepositoryのIG_ACCESS_TOKENを更新します。productionの同名Secretがある場合は優先されるため、保存先を統一してください。",
        "設定の有無だけの検査です。トークンの有効性・投稿成功は未検証です。",
    ]
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as file:
            file.write("\n".join(summary) + "\n")
    print(config["reason"])
    if not config["ready"]:
        print("::error::" + config["reason"])
        sys.exit(1)


if __name__ == "__main__":
    main()
