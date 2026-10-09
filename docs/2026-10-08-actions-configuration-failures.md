# 自動投稿とトークン延長の設定不足を判別する

## 確認した原因

- トークン延長の実行37702880492（2026-10-08 08:32 JST）は、GH_PAT未設定で延長APIの前に停止。
- 投稿の実行37560591329（2026-10-07 11:09 JST）は、IG_USER_IDまたはIG_ACCESS_TOKEN未設定で停止。
- 同じ投稿実行のメール通知もDIGEST_TO、SMTP_USER、SMTP_PASS未設定で停止。
- Repository secretsとproduction環境のSecrets名一覧はいずれも空。値は取得していない。

## 変更

設定検査を共通化し、未設定の名前と対応先をActions Summaryに表示する。
Issue・設定済みの独自メールにも原因を載せる。設定不足による失敗は維持する。
メール未設定は警告とSummaryに記録し、投稿・延長に通知処理の二次障害を重ねない。
番号指定を環境変数とシェル配列で渡し、投稿済み番号の本番再投稿を拒否する。
延長APIの応答やトークンがエラーログに出ないようにする。
Secretsを使わないunittestとdry-runの検証ワークフローを追加する。

## 残る本人操作と確認

IG_USER_ID、IG_ACCESS_TOKEN、GH_PATをRepository secretsへ登録する必要がある。
GH_PATはこのリポジトリ限定のSecrets書き込み権限が必要。新しい権限・認証情報の発行は本人が行う。
productionに同名トークンを登録すると延長結果より優先されるため、保存先を統一する。
メール経路にはDIGEST_TO、SMTP_USER、SMTP_PASSも必要。

このリポジトリのschedule.jsonには過去予定14件が残っている。
認証設定だけで投稿が復旧したとは扱わず、登録前に公開済み一覧との重複を確認する。
公開後にschedule.jsonの保存・pushが失敗した場合の重複リスクは残るので、再実行前の公開履歴照合が必要。
本番投稿・トークン延長・メール送信による検証は行っていない。

## ローカル検証

- `python -B -m unittest discover -s tests -v`: 40件成功。
- 延長API、SSL、投稿APIはmockで検査し、ネットワーク送信なし。
- dry-runはAPI呼び出しとschedule.jsonの変更がないことを検査。
- `bash -n setup.sh` と `git diff --check`: 成功。
- 4件のworkflow YAMLは解析成功。本番の認証有効性は未確認。

## 内容への影響

投稿原稿、画像、予定時刻、投稿済み記録、production承認設定、既存cronは変更していない。
科学内容の改稿を含まないためR1〜R5・健康区分の新規判定対象はない。
既存の認証情報と公開履歴の照合が未完了のため、本番実行の復旧は未完了。
