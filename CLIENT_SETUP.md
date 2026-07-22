# クライアントセットアップ

教育デモの初版では、ノートPCからSSHのポートフォワーディングでDebate APIへ接続する。

クライアント側にOllama、Tailscale、NetBirdをインストールする必要はない。

~~~text
ノートPC
  ├─ SSHクライアント
  ├─ ブラウザ
  └─ client/launch_demo.sh
        │
        │ localhost:8000
        ▼
SSHトンネル ── Ubuntuサーバーの127.0.0.1:8000
                         │
                         ▼
                    Debate API ── Ollama
~~~

## 1. 前提

- macOSまたはLinuxのノートPC
- `ssh` コマンド
- Webブラウザ
- サーバーへSSH接続できること
- サーバー上でDebate APIが起動していること

SSHの認証鍵やパスワードは、このリポジトリへ保存しない。既存のSSH設定、SSH agent、または利用者の認証方式を使う。

## 2. サーバー側の初回設定

サーバーではDebate APIをlocalhostだけで待ち受けさせる。

~~~bash
cd /opt/Debate
sudo DEBATE_USER=ubuntu DEBATE_BIND_HOST=127.0.0.1 \
  ./server/scripts/setup_ubuntu.sh \
  --overlay none \
  --model gemma4:31b
~~~

サーバー上で動作を確認する。

~~~bash
sudo systemctl status debate-api --no-pager
curl -fsS http://127.0.0.1:8000/health
~~~

## 3. クライアントへリポジトリを配置

ノートPCにリポジトリを配置する。

~~~bash
cd /path/to/Debate
chmod +x client/launch_demo.sh
~~~

クライアント側でPythonやOllamaを起動する必要はない。`launch_demo.sh` はAPIのヘルスチェック後に既定ブラウザを開く。

## 4. SSHトンネルを作成

ノートPCのターミナルで実行する。

~~~bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 8000:127.0.0.1:8000 \
  ubuntu@<server-host>
~~~

`<server-host>` は、SSHで接続するサーバーのホスト名またはIPアドレスに変更する。

このターミナルはSSHトンネル維持のため開いたままにする。終了するときは `Ctrl+C` を押す。

## 5. ブラウザを起動

別のターミナルで実行する。

~~~bash
DEBATE_URL=http://127.0.0.1:8000 ./client/launch_demo.sh
~~~

手動で開く場合は、ブラウザで次のURLへアクセスする。

~~~text
http://127.0.0.1:8000/
~~~

## 6. 接続確認

ブラウザを開く前に、クライアント側からヘルスチェックできる。

~~~bash
curl -fsS http://127.0.0.1:8000/health
~~~

期待する応答：

~~~json
{
  "status": "ok",
  "model": "gemma4:31b",
  "overlay_provider": "none",
  "ollama": "ok"
}
~~~

## 7. よくある問題

### SSH接続はできるがlocalhost:8000に接続できない

サーバー上でDebate APIを確認する。

~~~bash
sudo systemctl status debate-api --no-pager
curl -fsS http://127.0.0.1:8000/health
sudo journalctl -u debate-api -n 100 --no-pager
~~~

### ローカル8000番ポートが使用中

別のローカルポートへ転送する。

~~~bash
ssh -N \
  -L 18000:127.0.0.1:8000 \
  ubuntu@<server-host>
~~~

ブラウザURLも変更する。

~~~bash
DEBATE_URL=http://127.0.0.1:18000 ./client/launch_demo.sh
~~~

### SSHトンネルが切断される

SSHのkeepalive設定を確認する。上記コマンドの `ServerAliveInterval` と `ServerAliveCountMax` を使用する。

## 8. Tailscale / NetBirdを使う場合

複数クライアント、常時運用、オーバーレイ側のアクセス制御が必要になった場合は、 [SETUP_UBUNTU.md](SETUP_UBUNTU.md) のTailscaleまたはNetBird方式を使う。
