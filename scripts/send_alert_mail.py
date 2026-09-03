"""アラートをGmailへ送る。

Issueは記録として残すが、開きっぱなしで誰も見ないことがある。
気づける場所（Gmail）へも同じ内容を流すためのスクリプト。

送信はSMTPで行う。smtp.gmail.com:587 にSTARTTLSで接続し、
Gmailのアプリパスワードでログインする。

このリポジトリはPublicで、Actionsのログも公開される。
宛先アドレスと例外の本文は標準出力に出さない（宛先が混ざることがある）。

環境変数:
  DIGEST_TO             送信先メールアドレス
  SMTP_HOST             SMTPサーバ（既定 smtp.gmail.com）
  SMTP_PORT             SMTPポート（既定 587）
  SMTP_USER             SMTPユーザー名
  SMTP_PASS             SMTPパスワード（Gmailの場合はアプリパスワード）

  python scripts/send_alert_mail.py --subject "件名" --body-file body.txt
  python scripts/send_alert_mail.py --subject "件名" --body-file body.txt --check

--check は送信せず、必要な環境変数が揃っているかだけを見る（終了コードで返す）。
"""
import argparse, os, smtplib, sys
from email.message import EmailMessage

REQUIRED = ["DIGEST_TO", "SMTP_USER", "SMTP_PASS"]


def missing():
    """未設定の環境変数名を返す。HOSTとPORTは既定値があるので必須にしない。"""
    return [n for n in REQUIRED if not os.environ.get(n, "").strip()]


def send(subject, body):
    cfg = {
        "to": os.environ["DIGEST_TO"].strip(),
        "host": os.environ.get("SMTP_HOST", "").strip() or "smtp.gmail.com",
        "port": int(os.environ.get("SMTP_PORT", "").strip() or "587"),
        "user": os.environ["SMTP_USER"].strip(),
        "password": os.environ["SMTP_PASS"],
    }
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]
    msg.set_content(body)

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as s:
        s.starttls()
        s.login(cfg["user"], cfg["password"])
        s.send_message(msg)
    # 公開ログなので宛先は出さない
    print("アラートを送信しました。")


def main():
    ap = argparse.ArgumentParser(description="アラートをGmailへ送る")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body-file", help="本文のファイル（未指定なら標準入力）")
    ap.add_argument("--check", action="store_true", help="送信せず設定の有無だけ確認する")
    args = ap.parse_args()

    lack = missing()
    if lack:
        # 未設定は「設定漏れ」。黙って成功させない。
        print(f"::error::メール通知のSecretsが未設定です（{', '.join(lack)}）。"
              "README.md のSecrets表を見て登録してください。"
              if os.environ.get("GITHUB_ACTIONS")
              else f"エラー: メール通知のSecretsが未設定です（{', '.join(lack)}）")
        sys.exit(1)
    if args.check:
        print("メール通知のSecretsは揃っています。")
        return

    if args.body_file:
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()
    else:
        body = sys.stdin.read()

    try:
        send(args.subject, body)
    except Exception as e:
        # 公開ログなので例外の本文は出さない。SMTPRecipientsRefused などは
        # 宛先アドレスを含む。デバッグ性より漏えい防止を優先し、種類だけを出す。
        kind = type(e).__name__
        print(f"::error::メール送信に失敗しました（{kind}）。SMTP系のSecretsを確認してください。"
              if os.environ.get("GITHUB_ACTIONS")
              else f"エラー: メール送信に失敗しました（{kind}）")
        sys.exit(1)


if __name__ == "__main__":
    main()
