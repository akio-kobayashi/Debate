# Ubuntuサーバーセットアップスクリプト設計

> 2026-07-22改訂：当初のTailscale専用分割案に代えて、初版実装では `setup_ubuntu.sh --overlay tailscale|netbird|none` を採用する。認証はどちらも手動のままにし、Ollamaのlocalhost限定とDebate APIのsystemd化を共通化する。詳細な実行手順は [SETUP_UBUNTU.md](SETUP_UBUNTU.md) を参照する。

## 1. 目的

OLLAMA_SERVER_SETUP.mdの手順を、Ubuntuサーバー上で再実行できるスクリプト群として設計する。

スクリプトは次を満たす。

- 初回セットアップを自動化する
- 途中で失敗しても同じコマンドを再実行できる
- 既存のOllama設定を不用意に破壊しない
- Tailscaleの認証情報をファイルやログへ残さない
- Ollamaをlocalhostに限定する
- 最後に動作確認を自動実行する

この段階では設計のみとし、スクリプトの実装はPhase 0で行う。

## 2. スクリプト構成

```text
Debate/server/scripts/
├── common.sh
├── 00_check_prerequisites.sh
├── 10_install_ollama.sh
├── 20_configure_ollama.sh
├── 30_pull_model.sh
├── 40_install_tailscale.sh
├── 50_verify_ollama.sh
├── 60_verify_tailscale.sh
└── setup_server.sh
```

### common.sh

全スクリプトから呼び出す共通処理。

- bashの安全設定
- root権限確認
- Ubuntu判定
- CPUアーキテクチャ取得
- ログ出力
- コマンド存在確認
- エラー時の終了メッセージ
- 設定値の読み込み

共通設定の初期値：

```bash
OLLAMA_MODEL="gemma4:31b"
OLLAMA_HOST="127.0.0.1:11434"
OLLAMA_NO_CLOUD="1"
DEBATE_NUM_CTX="8192"
```

設定値は環境変数またはコマンドライン引数で上書きできる。秘密情報は受け取らない。

### 00_check_prerequisites.sh

セットアップ前の検査のみを行う。システムを変更しない。

確認項目：

- Ubuntuであること
- sudoが利用できること
- curl、ca-certificatesが利用可能またはaptで導入可能であること
- amd64またはarm64であること
- 空きディスク容量
- 空きRAM
- NVIDIA GPUの有無
- NVIDIA GPUがある場合のnvidia-smi
- 外向きHTTPS接続
- 既存の11434番ポート使用状況

GPUドライバーは自動インストールしない。GPUごとに導入方法が異なるため、検出結果だけを表示する。

### 10_install_ollama.sh

Ollama本体とsystemdサービスを準備する。

処理順：

1. aptのパッケージ一覧を更新する。
2. curlとca-certificatesを導入する。
3. Ollama公式インストールスクリプトを実行する。
4. ollamaコマンドの存在を確認する。
5. ollama.serviceの存在を確認する。
6. systemdをreloadする。
7. Ollamaをenable --nowする。
8. localhostのAPI応答を確認する。

再実行時：

- ollamaコマンドが存在する場合はインストールをスキップする。
- サービスが起動済みなら再起動せず、状態だけ確認する。
- 失敗時はjournalctlの確認コマンドを表示する。

### 20_configure_ollama.sh

Ollamaのsystemd overrideを作成する。

作成先：

```text
/etc/systemd/system/ollama.service.d/override.conf
```

設定内容：

```ini
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NO_CLOUD=1"
```

設計上の制約：

- OLLAMA_HOSTは127.0.0.1:11434にする。
- 0.0.0.0:11434を自動設定しない。
- 既存のoverrideを無条件に上書きしない。
- 既存設定との差分を確認してから更新する。
- 更新した場合だけdaemon-reloadとrestartを行う。
- モデル名はOllamaサービスではなく、モデル取得スクリプトとDebate APIで扱う。

### 30_pull_model.sh

予定モデルを取得する。

```bash
OLLAMA_MODEL="gemma4:31b"
ollama pull "$OLLAMA_MODEL"
```

引数例：

```text
./30_pull_model.sh
./30_pull_model.sh --model gemma4:31b
./30_pull_model.sh --model gemma4:12b
```

- デフォルトはgemma4:31b。
- 別モデルを指定できるが、初版の受け入れ条件はgemma4:31bに固定する。
- モデル取得前に空きディスクを確認する。
- 取得後にollama listで存在を確認する。
- モデル削除処理は実装しない。

### 40_install_tailscale.sh

Tailscaleクライアントをインストールする。

処理：

1. Tailscale公式インストールスクリプトを実行する。
2. tailscaleコマンドの存在を確認する。
3. tailscaledサービスの状態を確認する。
4. サーバー登録方法を表示する。

重要な制約：

- 自動的にtailscale upを実行しない。
- auth keyをスクリプト、設定ファイル、ログへ保存しない。
- Tailnet、ACL、端末名は利用者が決定する。

手動接続：

```bash
sudo tailscale up
tailscale status
tailscale ip -4
```

### 50_verify_ollama.sh

Ollamaとモデルのローカル動作を検証する。

確認項目：

```bash
systemctl is-active --quiet ollama
curl -fsS http://127.0.0.1:11434/api/tags
ollama list
ollama ps
ss -ltnp
```

さらに、gemma4:31bへ短い日本語プロンプトを送り、次を確認する。

- HTTPエラーにならない
- JSON応答が返る
- message.contentが空でない
- 応答時間を記録できる
- GPU/CPUの配置を表示できる

初期動作確認ではnum_ctxを8192とする。

### 60_verify_tailscale.sh

Tailscale登録後に実行する検証スクリプト。

確認項目：

- tailscale statusが成功する
- サーバーにTailscale IPがある
- tailscaledが稼働している
- Tailscale DNS名を取得できる
- Ollamaの11434番が外部待ち受けしていない

Debate API未実装の段階では、クライアントからのAPI到達確認はスキップする。

### setup_server.sh

各スクリプトを決められた順番で呼ぶオーケストレーター。

標準実行：

```bash
sudo ./server/scripts/setup_server.sh --model gemma4:31b
```

実行順：

```text
00_check_prerequisites.sh
10_install_ollama.sh
20_configure_ollama.sh
30_pull_model.sh
40_install_tailscale.sh
50_verify_ollama.sh
手動: sudo tailscale up
60_verify_tailscale.sh
```

オプション：

```text
--model <name>       取得するモデルを変更する
--skip-model-pull   モデル取得をスキップする
--skip-tailscale    Tailscaleの導入をスキップする
--check-only        事前確認だけを行う
--help              使用方法を表示する
```

setup_server.shはTailscaleの接続認証を自動実行しない。終了時に、利用者が次に実行するコマンドを表示する。

## 3. 変更範囲

スクリプトが変更するもの：

- Ollamaの実行ファイル
- Ollamaのsystemdサービス
- Ollamaのsystemd override
- Ollamaのモデル格納領域
- Tailscaleのパッケージとサービス
- Tailscaleのローカル状態

スクリプトが変更しないもの：

- UbuntuのGPUドライバー
- 既存モデルの削除
- UFWの既存ルール
- Tailnet ACL
- Tailscaleの認証状態
- Debate APIのアプリケーションコード

## 4. 安全性と再実行性

すべての実行スクリプトは次の方針とする。

```bash
set -Eeuo pipefail
```

- root権限が必要な処理は開始時に確認する。
- curlの通信失敗を無視しない。
- 変更前に対象ファイルの存在と内容を確認する。
- 既存overrideを無条件に消さない。
- rmやアンインストール処理を含めない。
- 既存モデルを削除しない。
- 失敗時は終了コードを0以外にする。
- 実行した処理と次の確認コマンドを表示する。
- auth keyや機密情報を標準出力へ表示しない。

systemd設定の更新は、内容が変わったときだけサービスを再起動する。

## 5. ログ設計

通常のログは標準出力へ出す。

表示する項目：

- 実行中のスクリプト名
- 実行中の処理
- 成功した確認項目
- 失敗した確認項目
- 失敗時の復旧・確認コマンド

表示してはいけないもの：

- Tailscale auth key
- APIトークン
- パスワード
- プロンプトや生成内容の全文

## 6. 実装フェーズへの組み込み

サーバー実装計画のPhase 0を次の順にする。

1. セットアップスクリプトをUbuntuへコピーする。
2. check-onlyで前提条件を確認する。
3. Ollamaをインストールする。
4. Ollamaをlocalhostへ限定する。
5. gemma4:31bを取得する。
6. OllamaのHTTP APIとGPU/CPU配置を確認する。
7. Tailscaleをインストールする。
8. 手動でtailscale upを実行する。
9. Tailscale状態を確認する。
10. Phase 1のFastAPI実装へ進む。

### Phase 0の完了条件

- setup_server.shを2回実行しても破綻しない。
- Ollamaがsystemdで自動起動する。
- gemma4:31bが取得済みになる。
- 127.0.0.1:11434からAPI応答がある。
- 11434が0.0.0.0で待ち受けていない。
- Tailscaleの接続手順が利用者に明示される。
- Tailscale登録後にverify_tailscale.shが成功する。

## 7. 将来追加するスクリプト

初版では作らない。

- Debate APIのsystemdサービス登録
- Tailscale Serveの設定
- Debate APIのアプリケーション環境作成
- データベース初期化
- アプリケーションの更新・ロールバック
- アプリケーション独自の認証設定

Debate API実装後は、Ollamaの11434ではなく、Debate APIのlocalhostポートだけをTailscale Serveで公開する。
