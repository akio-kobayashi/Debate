# Google Forms / Drive連携

> この文書は旧版の拡張機能用です。初版ではGoogle Forms / Drive連携を使用せず、画面の「PDFをダウンロード」で結果を保存します。旧版APIも外部処理を開始しないよう無効化しています。

Debate Demoは、ディベート終了後に次の2つをGoogle Driveへ保存できます。

- アンケート回答用の論点参照資料
- Google Form回答の集計・Cによる分析レポート

OAuthのクライアントJSON、アクセストークン、学生の回答データはリポジトリへ保存しません。

## 1. Google Cloud側の準備

1. Google Cloudプロジェクトを作成する。
2. Google Forms APIとGoogle Drive APIを有効にする。
3. OAuth同意画面を設定する。
4. OAuthクライアントで「デスクトップアプリ」を作成する。
5. ダウンロードしたJSONを、Ubuntuサーバー上のリポジトリ外へ置く。

使用する権限は次の3つです。

```text
https://www.googleapis.com/auth/drive.file
https://www.googleapis.com/auth/forms.body.readonly
https://www.googleapis.com/auth/forms.responses.readonly
```

## 2. OAuth認証

サーバー側の仮想環境で、次を実行します。

```bash
cd /path/to/Debate
sudo mkdir -p /etc/debate
sudo chmod 700 /etc/debate
sudo cp /path/to/client_secret.json /etc/debate/google-client-secrets.json
sudo chmod 600 /etc/debate/google-client-secrets.json

sudo -u <debate-user> server/.venv/bin/python \
  server/scripts/authorize_google.py \
  --credentials /etc/debate/google-client-secrets.json \
  --token /etc/debate/google-token.json \
  --port 8765 \
  --no-browser
```

SSHトンネル方式では、認証前に別のターミナルで次を実行します。

```bash
ssh -N -L 8765:127.0.0.1:8765 <user>@<server-host>
```

表示された認証URLをノートPCのブラウザで開き、認証後にリダイレクトを完了させます。

## 3. 環境変数

`/etc/debate-api.env`には、秘密情報そのものではなく、IDとファイルパスだけを設定します。

```text
GOOGLE_FORM_ID=<response-form-id>
GOOGLE_DRIVE_FOLDER_ID=<destination-folder-id>
GOOGLE_OAUTH_CLIENT_SECRETS=/etc/debate/google-client-secrets.json
GOOGLE_OAUTH_TOKEN=/etc/debate/google-token.json
```

Form IDは、回答を取得するGoogle FormのIDです。Driveフォルダは、参照資料と分析レポートの保存先です。共有設定はDrive側で行い、アプリから一般公開設定は変更しません。

設定後はAPIを再起動します。

```bash
sudo systemctl restart debate-api
curl http://127.0.0.1:8000/health
```

`health`の`google_workspace`が`configured`になれば、設定値が揃っています。OAuthトークンが無効な場合は、認証スクリプトを再実行してください。

## 4. 画面上の操作

ディベート終了後、教員が次の順に操作します。

1. 「参照資料を生成」
2. 「回答受付開始」
3. 学生が参照資料を確認してGoogle Formへ回答
4. 「回答を分析」
5. 「分析結果を表示」またはGoogle Driveのレポートを開く

集計値はサーバーで計算し、Cには集計済みの値だけを渡します。回答者個人の回答内容は分析結果やDriveレポートには保存しません。
