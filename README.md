# Debate Demo

ローカルLLMを使ったA・B・C三役のディベートデモです。ブラウザ画面、FastAPI製Debate API、Ollama接続、Ubuntuセットアップを含みます。

## 構成

~~~text
ノートPCのブラウザ
        │ Tailscale または NetBird
        ▼
Debate API・Web画面 ── localhost ── Ollama
~~~

Ollamaは外部公開せず、Debate APIだけをクライアントへ公開します。接続方式はTailscale、NetBird、SSHトンネルから選択できます。

## Ubuntuサーバー

詳細は [SETUP_UBUNTU.md](SETUP_UBUNTU.md) を参照してください。

Ollamaの単独の導入・更新方法は [ollama.md](ollama.md) にまとめています。

Tailscale Serveを使う場合：

~~~bash
sudo DEBATE_USER=ubuntu ./server/scripts/setup_ubuntu.sh \
  --overlay tailscale \
  --model gemma4:31b \
  --tailscale-serve
~~~

NetBirdを使う場合：

~~~bash
sudo DEBATE_USER=ubuntu ./server/scripts/setup_ubuntu.sh \
  --overlay netbird \
  --model gemma4:31b
~~~

`tailscale up` または `netbird up` は、認証情報を保存しないため手動で実行します。

SSHトンネルを使う場合：

~~~bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 8000:127.0.0.1:8000 \
  ubuntu@<server-host>
~~~

別のターミナルでブラウザを開きます。

~~~bash
DEBATE_URL=http://127.0.0.1:8000 ./client/launch_demo.sh
~~~

## クライアント

ノートPC側で、APIのURLを指定してブラウザを開きます。

~~~bash
DEBATE_URL=https://<server-name>.<tailnet-name>.ts.net ./client/launch_demo.sh
~~~

## API

- `POST /api/debates`：テーマからセッションを作成
- `GET /api/debates/{id}/events`：SSE購読
- `POST /api/debates/{id}/next`：次の発言を開始
- `POST /api/debates/{id}/stop`：生成を停止
- `POST /api/debates/{id}/reset`：セッションを初期化
- `GET /health`：サービスとモデルの確認

ターン順はサーバー側で固定し、LLM同時実行数は1に制限します。
