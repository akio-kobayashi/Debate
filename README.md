# Debate Demo

ローカルLLMを使ったA・B・C三役のディベートデモです。ブラウザ画面、FastAPI製Debate API、Ollama接続、Ubuntuセットアップを含みます。

## 構成

~~~text
ノートPCのブラウザ
        │ SSHトンネル（初版） / Tailscale / NetBird
        ▼
Debate API・Web画面 ── localhost ── Ollama
~~~

Ollamaは外部公開せず、Debate APIだけをクライアントへ公開します。教育デモの初版ではSSHトンネルを標準方式とし、TailscaleとNetBirdは複数端末や常時運用が必要になった場合の選択肢とします。

## Ubuntuサーバー

全体のセットアップ・起動・更新手順は [SETUP.md](SETUP.md) にまとめています。

Ollamaの単独の導入・更新方法は [ollama.md](ollama.md) にまとめています。

クライアント側のSSHトンネル手順は [CLIENT_SETUP.md](CLIENT_SETUP.md) にまとめています。

SSHトンネルを使う場合（推奨）：

~~~bash
sudo DEBATE_USER=ubuntu DEBATE_BIND_HOST=127.0.0.1 \
  ./server/scripts/setup_ubuntu.sh \
  --overlay none \
  --model gemma4:31b
~~~

ノートPCからSSH転送を作成します。

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

Tailscale Serveを使う場合（任意）：

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

## クライアント

ノートPC側で、APIのURLを指定してブラウザを開きます。

~~~bash
DEBATE_URL=http://127.0.0.1:8000 ./client/launch_demo.sh
~~~

## API

- `POST /api/debates`：テーマからセッションを作成
- `GET /api/debates/{id}/events`：SSE購読
- `POST /api/debates/{id}/next`：次の発言を開始
- `POST /api/debates/{id}/stop`：生成を停止
- `POST /api/debates/{id}/reset`：セッションを初期化
- `GET /health`：サービスとモデルの確認

ターン順はサーバー側で固定し、LLM同時実行数は1に制限します。
