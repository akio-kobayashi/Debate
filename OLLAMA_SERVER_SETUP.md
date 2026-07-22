# Ollamaサーバーセットアップ手順（Ubuntu）

ローカルLLMディベートデモの推論サーバーをUbuntu上に構築する手順。

## 1. この手順で構築するもの

```text
Ubuntu server
  ├─ Ollama
  │    └─ gemma4:31b
  ├─ Tailscale または NetBird
  └─ localhost:11434 のOllama API
```

初版の構成では、ブラウザからOllama APIへ直接接続しない。後で同じサーバー上にDebate APIを配置し、Debate APIだけをTailscale経由でブラウザへ公開する。

```text
ブラウザ ── Tailscale / NetBird ── Debate API ── localhost ── Ollama
```

したがって、Ollamaのポート `11434` をTailnetやインターネットへ公開する設定は、この段階では行わない。

## 2. 前提

- Ubuntu 22.04 LTSまたは24.04 LTSを想定する。
- CPUアーキテクチャは、標準手順では amd64 を想定する。
- GPUを使用する場合は、Ubuntu側のGPUドライバーが導入済みであること。
- モデルの取得にインターネット接続が必要。
- 管理者権限（`sudo`）が必要。
- `gemma4:31b` のモデルサイズはOllamaのモデルページ上で約20GB。モデル本体に加えて、推論時のVRAM・RAM、コンテキスト用メモリ、空きディスクを確保する。

31Bモデルが実際にGPUへ載るかどうかは、GPUのVRAM、量子化、コンテキスト長などで変わる。モデルサイズだけで必要VRAMを判断せず、導入後に `ollama ps` で確認する。

## 3. OSとGPUの事前確認

```bash
cat /etc/os-release
uname -m
free -h
df -h /
```

NVIDIA GPUを使う場合は、まず次を確認する。

```bash
nvidia-smi
```

`nvidia-smi` が見つからない、またはGPU情報が表示されない場合は、Ollamaの導入前にUbuntu向けNVIDIAドライバーを整える。ドライバーの種類はサーバーのGPUとUbuntuのバージョンに合わせて決める。

## 4. Ollamaのインストール

公式のLinuxインストール手順を使用する。

```bash
sudo apt-get update
sudo apt-get install -y curl ca-certificates
curl -fsSL https://ollama.com/install.sh | sh
```

インストール後、コマンドが利用できることを確認する。

```bash
command -v ollama
ollama --version
```

## 5. Ollamaのsystemdサービスを起動

サービスが登録されていることを確認する。

```bash
systemctl cat ollama.service
```

サービスが存在する場合は、起動と自動起動を有効にする。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ollama
sudo systemctl status ollama --no-pager
```

次のコマンドで、APIがlocalhostから応答することを確認する。

```bash
curl -fsS http://127.0.0.1:11434/api/tags
```

`systemctl cat ollama.service` でサービスが見つからない場合は、公式Linux手順に従って `ollama` ユーザーとsystemdユニットを作成してから、上記の起動コマンドを実行する。

## 6. Ollamaのネットワーク設定

Ollamaは既定で `127.0.0.1:11434` にバインドされる。今回の構成では、Debate APIが同じサーバー上でOllamaを利用するため、この設定を維持する。

設定を明示的に固定する場合は、systemdのoverrideを作成する。

```bash
sudo systemctl edit ollama.service
```

エディターが開いたら、次を記入する。

```ini
[Service]
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_NO_CLOUD=1"
```

保存後、サービスを再起動する。

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
sudo systemctl status ollama --no-pager
```

`OLLAMA_NO_CLOUD=1` は、今回の用途をローカルモデルに限定するための設定である。クラウドモデルやOllamaのクラウド機能を使う予定がある場合は、この行を追加しない。

### 外部公開について

次の設定は、今回の初版では使用しない。

```ini
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

これは全インターフェースで待ち受ける設定であり、認証・ファイアウォール・Tailnet ACLを別途設計する必要がある。Debate APIを同一サーバーで動かす間は、Ollamaをlocalhostに限定する。

## 7. モデルの取得

予定モデルを取得する。

```bash
ollama pull gemma4:31b
```

取得結果を確認する。

```bash
ollama list
```

一覧に次のモデルが表示されることを確認する。

```text
gemma4:31b
```

## 8. CLIでの動作確認

短いプロンプトでモデルが応答することを確認する。

```bash
ollama run gemma4:31b "日本語で一文だけ自己紹介してください。"
```

終了するには `Ctrl+D` または `Ctrl+C` を使用する。

## 9. HTTP APIでの動作確認

ディベートAPIから利用する予定の `/api/chat` を直接テストする。

```bash
curl -N http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gemma4:31b",
    "messages": [
      {
        "role": "user",
        "content": "日本語で一文だけ自己紹介してください。"
      }
    ],
    "stream": false,
    "options": {
      "num_ctx": 32768
    }
  }'
```

確認する点は次のとおり。

- HTTPエラーにならない。
- JSONレスポンスが返る。
- `message.content` に日本語の応答が含まれる。
- 応答が極端に遅くない。

`num_ctx: 32768` はRTX A6000 48GBを前提にした初期値である。Gemma 4の最大コンテキスト長を制限する値ではない。実機のVRAM使用量と生成速度を確認し、必要ならOLLAMA_NUM_CTXで変更する。

## 10. GPUへの配置確認

APIまたはCLIで一度モデルを実行した後、モデルの配置を確認する。

```bash
ollama ps
```

`PROCESSOR` 列を確認する。

- `100% GPU`：全体がGPU上で動作
- `100% CPU`：CPU・システムメモリ上で動作
- `CPU/GPU` の混在：一部がシステムメモリへオフロード

ディベートデモでは、応答速度と安定性のため、可能な限りGPU上で動作させる。GPUに載り切らない場合は、コンテキスト長を下げる、別のモデルサイズを検討する、またはサーバーのメモリ構成を見直す。

## 11. オーバーレイネットワークの導入

初版では、TailscaleまたはNetBirdのどちらか一方を選択する。自動セットアップを使う場合は [SETUP_UBUNTU.md](SETUP_UBUNTU.md) を参照する。

Tailscaleは、後でDebate APIをブラウザへ公開するためにサーバーへ導入する。Ollamaの `11434` を直接公開するためには使用しない。

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`sudo tailscale up` の実行時に表示されるURLを開き、サーバーを利用するTailnetへ登録する。

登録状態を確認する。

```bash
tailscale status
tailscale ip -4
```

### Tailscaleの確認方針

- サーバーがTailnet上でオンラインになっていること。
- クライアント端末も同じTailnetに参加していること。
- TailnetのACLで、将来のDebate APIへのアクセス元を制限すること。
- この段階では、クライアントから `http://<server>:11434` を直接開かないこと。

Debate APIがlocalhostのポート（例：`8000`）で動くようになった後、次のようにTailscale ServeでTailnet内へ公開する。

```bash
tailscale serve 8000
```

このコマンドはDebate API完成後に実行する。Tailscale ServeでHTTPSを使うには、TailnetでHTTPS証明書を有効にする必要がある。

## 12. ログとトラブルシューティング

Ollamaサービスの状態を確認する。

```bash
sudo systemctl status ollama --no-pager
sudo journalctl -u ollama -n 100 --no-pager
```

APIが応答しない場合は、次を順番に確認する。

```bash
sudo systemctl is-active ollama
ss -ltnp | grep 11434
curl -v http://127.0.0.1:11434/api/tags
```

モデル取得に失敗した場合は、ディスク容量と外向きHTTPS接続を確認する。

```bash
df -h /
curl -I https://ollama.com
```

GPUが使われない場合は、次を確認する。

```bash
nvidia-smi
ollama ps
sudo journalctl -u ollama -n 200 --no-pager
```

## 13. セットアップ完了チェックリスト

- [ ] Ubuntuのバージョンとアーキテクチャを確認した
- [ ] GPUドライバーを確認した（GPUを使う場合）
- [ ] Ollamaをインストールした
- [ ] `ollama` systemdサービスを有効化した
- [ ] `http://127.0.0.1:11434/api/tags` が応答した
- [ ] `gemma4:31b` を取得した
- [ ] CLIで日本語応答を確認した
- [ ] HTTP APIで応答を確認した
- [ ] `ollama ps` でCPU/GPUの配置を確認した
- [ ] Tailscaleへサーバーを登録した
- [ ] Ollamaの `11434` を外部公開していない

## 参照

- [Ollama Linux installation](https://docs.ollama.com/linux)
- [Ollama FAQ: server configuration and network binding](https://docs.ollama.com/faq)
- [Gemma 4 model page](https://ollama.com/library/gemma4)
- [Tailscale Linux installation](https://tailscale.com/docs/install/linux)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
