# Ubuntuサーバーセットアップ

Debate Demoの初版サーバーは、Ubuntu上でOllamaとDebate APIを同じマシンに配置する。

~~~text
ノートPCのブラウザ
        │
        │ Tailscale / NetBird / SSHトンネル
        ▼
Debate API : 8000 ── localhost ── Ollama : 11434
        │
        └── demo/index.html
~~~

OllamaのAPIは **127.0.0.1:11434** に限定する。ノートPCからOllamaへ直接接続せず、ブラウザはDebate APIだけを利用する。OllamaのLinux導入方法、チャットAPI、ストリーミングの仕様は公式ドキュメントに合わせる。

- [Ollama Linux installation](https://docs.ollama.com/linux)
- [Ollama Chat API](https://docs.ollama.com/api/chat)
- [Ollama streaming](https://docs.ollama.com/capabilities/streaming)

Ollama本体の更新方法は [ollama.md](ollama.md) に分離して記載する。

## 1. 前提

- Ubuntu 22.04 LTSまたは24.04 LTS
- sudo権限
- GPUドライバ導入済みであること（GPUを使用する場合）
- モデル取得用の外向きHTTPS通信
- **gemma4:31b** 用のディスク、RAM、VRAM

予定モデルは **gemma4:31b** とする。モデルを変更する場合は、セットアップ時に **--model** を指定する。

- [Gemma 4 model page](https://ollama.com/library/gemma4)
- [Qwen3 model page](https://ollama.com/library/qwen3)

GPUの導入状態は自動変更しない。必要に応じて、セットアップ前に次を確認する。

~~~bash
cat /etc/os-release
uname -m
free -h
df -h /
nvidia-smi
~~~

## 2. プロジェクトをサーバーへ配置

Debateディレクトリをサーバーへコピーする。例として **/opt/Debate** に配置した場合を示す。

~~~bash
sudo mkdir -p /opt
sudo cp -a Debate /opt/Debate
cd /opt/Debate
~~~

実際の配置先が利用者のホームディレクトリであれば、そのパスを後のコマンドに読み替える。

## 3. Tailscaleを使う場合（推奨）

Tailscaleを利用する場合は、セットアップスクリプトに **--overlay tailscale** を指定する。

~~~bash
cd /opt/Debate
sudo DEBATE_USER=ubuntu ./server/scripts/setup_ubuntu.sh \
  --overlay tailscale \
  --model gemma4:31b \
  --tailscale-serve
~~~

**DEBATE_USER=ubuntu** は、systemdでDebate APIを実行するUbuntuユーザー名に変更する。

スクリプトはTailscale本体を導入するが、端末登録は自動実行しない。公式手順に従って、サーバー上で明示的に登録する。

~~~bash
sudo tailscale up
tailscale status
tailscale ip -4
tailscale serve status
~~~

**--tailscale-serve** を指定した場合、Debate APIはlocalhostだけで待ち受け、Tailscale ServeがHTTPSの入口になる。Serveの対象はTailnet内に限定され、**tailscale serve --bg** は再起動後も設定を維持できる。HTTPS証明書を有効にしてから実行する必要がある。

- [Tailscale Linux installation](https://tailscale.com/docs/install/linux)
- [Tailscale Serve command](https://tailscale.com/docs/reference/tailscale-cli/serve)

Serveを使わず、Tailscale IPの8000番へ直接アクセスする構成も選べる。

~~~bash
cd /opt/Debate
sudo DEBATE_USER=ubuntu ./server/scripts/setup_ubuntu.sh \
  --overlay tailscale \
  --model gemma4:31b
sudo tailscale up
tailscale ip -4
~~~

この場合のクライアントURLは次の形式になる。

~~~text
http://<tailscale-ip>:8000/
~~~

ただし、APIを **0.0.0.0:8000** で待ち受けるため、UFWやホスト側ファイアウォールで8000番への接続元をTailscale側に限定すること。TailnetのACLまたはGrantでも、クライアントからDebateサーバーへの8000番だけを許可する。

- [Tailscale access control](https://tailscale.com/docs/features/access-control)
- [Tailscale policy syntax](https://tailscale.com/docs/reference/policy-syntax)

## 4. NetBirdを使う場合

NetBirdを利用する場合は、同じセットアップスクリプトに **--overlay netbird** を指定する。

~~~bash
cd /opt/Debate
sudo DEBATE_USER=ubuntu ./server/scripts/setup_ubuntu.sh \
  --overlay netbird \
  --model gemma4:31b
~~~

スクリプトはNetBird本体を導入するが、ネットワークへの登録は自動実行しない。登録方式に合わせて、setup keyまたは対話的なログインを実行する。

~~~bash
sudo netbird up
netbird status
~~~

クライアントURLは次の形式になる。

~~~text
http://<netbird-ip>:8000/
~~~

NetBirdの管理画面では、ノートPCを送信元、Debateサーバーを宛先、TCP 8000番を対象とするアクセスポリシーを作成する。ホスト側でUFWを使う場合は、NetBirdインターフェース **wt0** に対する8000番の許可も確認する。NetBirdの公式資料では、UFWがNetBirdのインターフェースと競合する場合があるため、既存のファイアウォールを確認してからルールを追加する。

- [NetBird Linux installation](https://docs.netbird.io/get-started/install/linux)
- [NetBird ports and firewalls](https://docs.netbird.io/about-netbird/ports-and-firewalls)
- [NetBird network access policies](https://docs.netbird.io/manage/access-control/manage-network-access)

## 5. オーバーレイを使わない場合

ローカルでの動作確認だけなら、**--overlay none** を指定できる。

~~~bash
cd /opt/Debate
sudo DEBATE_USER=ubuntu ./server/scripts/setup_ubuntu.sh \
  --overlay none \
  --model gemma4:31b
~~~

このモードでは、Debate APIを外部ネットワークへ公開する前提にしない。研究デモでノートPCから接続する場合は、Tailscale ServeまたはNetBird/Tailscaleの直接接続を使うこと。

SSHトンネルで接続する場合は、Debate APIをlocalhostだけで待ち受けさせる。

~~~bash
cd /opt/Debate
sudo DEBATE_USER=ubuntu DEBATE_BIND_HOST=127.0.0.1 \
  ./server/scripts/setup_ubuntu.sh \
  --overlay none \
  --model gemma4:31b
~~~

ノートPCからSSHトンネルを作成する。

~~~bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 8000:127.0.0.1:8000 \
  ubuntu@<server-host>
~~~

SSH接続を維持したまま、別のターミナルでブラウザを起動する。

~~~bash
DEBATE_URL=http://127.0.0.1:8000 ./client/launch_demo.sh
~~~

SSHトンネル方式では、サーバーのSSH認証とホスト鍵管理が接続制御になる。複数クライアントから同時利用する場合や、教室内の複数端末へ配布する場合は、TailscaleまたはNetBirdの方が運用しやすい。

## 6. クライアントを起動する

ノートPC側でDebateリポジトリを取得し、次のようにAPIのURLを渡す。

Tailscale Serveの場合：

~~~bash
DEBATE_URL=https://<server-name>.<tailnet-name>.ts.net \
  ./client/launch_demo.sh
~~~

Tailscale直接接続の場合：

~~~bash
DEBATE_URL=http://<tailscale-ip>:8000 \
  ./client/launch_demo.sh
~~~

NetBird直接接続の場合：

~~~bash
DEBATE_URL=http://<netbird-ip>:8000 \
  ./client/launch_demo.sh
~~~

スクリプトは **/health** を確認してから既定ブラウザを開く。ブラウザで次の表示が出れば、サーバー接続は成立している。

~~~json
{
  "status": "ok",
  "model": "gemma4:31b",
  "overlay_provider": "tailscale",
  "ollama": "ok"
}
~~~

## 7. サービス確認

~~~bash
sudo systemctl status ollama --no-pager
sudo systemctl status debate-api --no-pager
sudo journalctl -u debate-api -n 100 --no-pager
curl -fsS http://127.0.0.1:8000/health
ss -ltnp | grep -E '8000|11434'
ollama list
ollama ps
~~~

期待する分離は次のとおり。

- Ollamaは **127.0.0.1:11434**
- Debate APIはTailscale Serve利用時は **127.0.0.1:8000**
- Debate APIは直接接続時は **0.0.0.0:8000** とファイアウォールで保護

## 8. 変更可能な設定

セットアップスクリプトの主要な引数は次のとおり。

~~~text
--overlay netbird|tailscale|none
--model gemma4:31b
--tailscale-serve
--skip-model
--project-dir /opt/Debate
~~~

モデルをQwenへ切り替える例：

~~~bash
sudo DEBATE_USER=ubuntu ./server/scripts/setup_ubuntu.sh \
  --overlay tailscale \
  --model qwen3:32b \
  --tailscale-serve
~~~

モデルを変更した場合、ブラウザ上部のモデル表示は現状固定文字列なので、初版ではAPIの **/health** の値を確認する。次の小改修で、画面上部のモデル名を **/health** から動的に表示する。

## 9. セキュリティ上の境界

- Ollamaの11434番を外部に公開しない。
- **tailscale up** と **netbird up** は手動で実行し、認証キーをスクリプトへ埋め込まない。
- 直接接続モードで8000番を全インターフェースに公開する場合は、必ずUFWとオーバーレイ側ポリシーを設定する。
- Tailscale Serveを使う場合も、TailnetのACLまたはGrantで利用者を限定する。
- Debate APIには初版ではユーザー認証を実装していない。学内デモのアクセス制御は、まずオーバーレイネットワーク側で行う。
