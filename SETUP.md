# Debate Demo 全体セットアップ・運用手順

この文書を、Debate Demoの導入からデモ実行、更新、トラブル対応までの基準手順とする。

教育目的の初版では、TailscaleやNetBirdを使わず、SSHのポートフォワーディングで接続する。

## 1. 全体構成

~~~text
ノートPC
  ├─ SSHクライアント
  ├─ ブラウザ
  └─ Debateリポジトリ
        │
        │ localhost:8000
        ▼
SSHトンネル
        │
        ▼
Ubuntuサーバー
  ├─ Debate API / Web画面 : 127.0.0.1:8000
  │      │
  │      ▼
  └─ Ollama : 127.0.0.1:11434
           └─ gemma4:31b
~~~

役割は次のとおり。

- Ollama：LLM推論
- Debate API：A・B・Cの役割、10ターンの進行、プロンプト生成、SSE配信
- Web画面：Debate APIが配信するブラウザ画面
- SSHトンネル：ノートPCからサーバーのDebate APIへ接続

OllamaだけではDebate Demoは動作しない。Debate APIも起動しておく必要がある。

## 2. 前提

### Ubuntuサーバー

- Ubuntu 22.04 LTSまたは24.04 LTS
- sudo権限
- GPUを使う場合はGPUドライバ導入済み
- `gemma4:31b` を保存・実行できるディスク、RAM、VRAM
- モデル取得用の外向きHTTPS通信
- ノートPCからSSH接続できること

### ノートPC

- macOSまたはLinux
- `ssh` コマンド
- `curl` コマンド
- Webブラウザ
- Debateリポジトリ

SSH鍵、パスワード、秘密情報はリポジトリへ保存しない。

## 3. サーバーへDebateを配置

例として、サーバーの `/opt/Debate` に配置する。

~~~bash
sudo mkdir -p /opt
sudo cp -a Debate /opt/Debate
cd /opt/Debate
~~~

利用するパスに応じて、以後の `/opt/Debate` を読み替える。

## 4. サーバーを初回セットアップ

教育デモの標準構成では、オーバーレイネットワークを使わず、Debate APIをlocalhostだけで待ち受けさせる。

~~~bash
cd /opt/Debate
sudo DEBATE_USER=ubuntu DEBATE_BIND_HOST=127.0.0.1 \
  ./server/scripts/setup_ubuntu.sh \
  --overlay none \
  --model gemma4:31b
~~~

`DEBATE_USER=ubuntu` は、Debate APIを実行するUbuntuユーザー名に変更する。

このスクリプトは次を実行する。

1. 必要なUbuntuパッケージを導入
2. Ollamaを導入
3. Ollamaをsystemdサービスとして起動
4. `OLLAMA_HOST=127.0.0.1:11434` を設定
5. `gemma4:31b` を取得
6. Debate API用Python仮想環境を作成
7. PDF用の日本語フォントとPython依存関係を導入
8. Debate APIをsystemdサービスとして起動
9. localhostのヘルスチェックを実行

TailscaleやNetBirdを使わないため、`--overlay none` を指定する。

コンテキスト長の初期値は `OLLAMA_NUM_CTX=32768` とする。RTX A6000 48GBでは8Kに固定する必要はない。さらに長くする場合は、セットアップ時に環境変数で変更できる。

~~~bash
sudo OLLAMA_NUM_CTX=65536 \
  DEBATE_USER=ubuntu DEBATE_BIND_HOST=127.0.0.1 \
  ./server/scripts/setup_ubuntu.sh \
  --overlay none \
  --model gemma4:31b
~~~

## 5. サーバーの動作確認

~~~bash
sudo systemctl status ollama --no-pager
sudo systemctl status debate-api --no-pager

curl -fsS http://127.0.0.1:11434/api/tags
curl -fsS http://127.0.0.1:8000/health

ollama list
ollama ps
ss -ltnp | grep -E '8000|11434'
~~~

期待する待ち受け：

- Ollama：`127.0.0.1:11434`
- Debate API：`127.0.0.1:8000`

`/health` の例：

~~~json
{
  "status": "ok",
  "model": "gemma4:31b",
  "overlay_provider": "none",
  "ollama": "ok"
}
~~~

## 6. ノートPCからSSHトンネルを作成

ノートPC側で、SSH接続を維持したまま実行する。

~~~bash
cd /path/to/Debate

ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 8000:127.0.0.1:8000 \
  ubuntu@<server-host>
~~~

`<server-host>` は、SSH接続先のホスト名またはIPアドレスに変更する。

このターミナルはトンネル維持のため開いたままにする。終了時は `Ctrl+C` を押す。

## 7. ブラウザでDebate Demoを起動

別のターミナルで実行する。

~~~bash
cd /path/to/Debate
DEBATE_URL=http://127.0.0.1:8000 ./client/launch_demo.sh
~~~

スクリプトは `/health` を確認してから既定ブラウザを開く。

手動で開く場合：

~~~text
http://127.0.0.1:8000/
~~~

## 8. デモ中の操作

1. テーマを入力
2. 「次の発言」を押す
3. Cがテーマを整理
4. A、B、Cが固定された10ターンで発言
5. 生成中は次の操作を待つ
6. 必要に応じて「停止」
7. 最終ターン後にCのまとめを確認
8. Cのまとめを出発点に、学生同士の議論へ移行する
9. 「リセット」で次のテーマへ進む

LLM生成はサーバー全体で同時に1件だけ実行する。

## 9. 日常の起動・停止

サーバーのサービスはsystemdで管理する。tmuxは必要ない。

~~~bash
sudo systemctl start ollama
sudo systemctl start debate-api
~~~

停止：

~~~bash
sudo systemctl stop debate-api
sudo systemctl stop ollama
~~~

再起動：

~~~bash
sudo systemctl restart ollama
sudo systemctl restart debate-api
~~~

状態とログ：

~~~bash
sudo systemctl status ollama --no-pager
sudo systemctl status debate-api --no-pager
sudo journalctl -u ollama -n 100 --no-pager
sudo journalctl -u debate-api -n 100 --no-pager
~~~

## 10. Ollamaの更新

Ollama本体の更新：

~~~bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl daemon-reload
sudo systemctl restart ollama
ollama --version
~~~

モデルの更新：

~~~bash
ollama pull gemma4:31b
ollama list
ollama ps
~~~

Ollama本体の更新とモデル更新は別である。Ollama更新後にDebate APIを確認する。

初版ではアンケートやGoogle Drive連携を使用しない。完了後はブラウザの「PDFをダウンロード」から、
CのMarkdown形式の最終整理だけをPDFとして保存する。PDF生成に必要なreportlabは`server/requirements.txt`に含めている。

~~~bash
sudo systemctl status debate-api --no-pager
curl -fsS http://127.0.0.1:8000/health
~~~

## 11. モデルをQwenへ変更する場合

サーバーでモデルを取得する。

~~~bash
ollama pull qwen3:32b
~~~

Debate APIのsystemd環境ファイル `/etc/debate-api.env` の `OLLAMA_MODEL` を変更し、再起動する。

~~~bash
sudo systemctl edit debate-api
sudo systemctl daemon-reload
sudo systemctl restart debate-api
~~~

実際の環境変数は次で確認する。

~~~bash
sudo cat /etc/debate-api.env
~~~

## 12. クライアント側のトラブル

### ローカル8000番が使用中

18000番へ転送する。

~~~bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -L 18000:127.0.0.1:8000 \
  ubuntu@<server-host>
~~~

~~~bash
DEBATE_URL=http://127.0.0.1:18000 ./client/launch_demo.sh
~~~

### SSH接続はできるが画面が開かない

サーバー側で次を確認する。

~~~bash
curl -fsS http://127.0.0.1:8000/health
sudo systemctl status debate-api --no-pager
sudo journalctl -u debate-api -n 100 --no-pager
~~~

### SSHトンネルが切断される

`ServerAliveInterval` と `ServerAliveCountMax` を設定して再接続する。

## 13. Tailscale / NetBirdを使う場合

次の要件が出た場合だけ、SSHトンネルから切り替える。

- 複数のノートPCから同時に利用する
- SSH接続を毎回作成する運用を避ける
- Tailscale ACLやNetBird Access Policyで接続元を管理する
- Tailscale ServeでHTTPS URLを提供する

TailscaleまたはNetBirdを使う場合の詳細は [SETUP_UBUNTU.md](SETUP_UBUNTU.md) を参照する。

## 14. サーバー更新用スクリプト

アップデート後は、サーバー上で次のスクリプトを実行する。Python依存関係、`OLLAMA_MODEL`、`OLLAMA_NUM_CTX`を反映し、OllamaとDebate APIを再起動した後、APIのヘルスチェックを行う。

明示的に指定しない場合、`OLLAMA_NUM_CTX`は32768へ更新する。既存設定が8192の場合も、この既定値に置き換わる。

~~~bash
cd /opt/Debate
sudo ./server/scripts/update_server.sh
~~~

Ollama本体とモデルも更新する場合は、オプションを付ける。

~~~bash
sudo ./server/scripts/update_server.sh \
  --update-ollama \
  --pull-model
~~~

コード取得もスクリプトに含める場合は、`--pull-code`を付ける。このオプションは、サーバー側の作業ツリーに未コミット変更があると停止する。

~~~bash
sudo ./server/scripts/update_server.sh --pull-code
~~~

コンテキスト長を変更する場合は、環境変数で指定できる。

~~~bash
sudo OLLAMA_NUM_CTX=65536 \
  ./server/scripts/update_server.sh
~~~

## 15. 関連資料

- [クライアント設計](CLIENT_DESIGN.md)
- [サーバー実装計画](SERVER_IMPLEMENTATION_PLAN.md)
- [基本仕様](SPEC.md)
- [Ollama単独の更新手順](ollama.md)
- [Debate APIのソース](server/app/main.py)
