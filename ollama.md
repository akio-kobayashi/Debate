# Ollamaの導入・更新手順

全体の導入・運用手順は [SETUP.md](SETUP.md) を基準とする。この文書はOllama単独の補足資料である。

Debate Demoでは、Ubuntuサーバー上のOllamaをsystemdサービスとして利用する。

OllamaのAPIは外部公開せず、Debate APIからlocalhost経由で接続する。

~~~text
Debate API ── http://127.0.0.1:11434 ── Ollama
~~~

## インストール

Ubuntuサーバーで実行する。

~~~bash
sudo apt-get update
sudo apt-get install -y curl ca-certificates
curl -fsSL https://ollama.com/install.sh | sh
~~~

サービスを有効化する。

~~~bash
sudo systemctl enable --now ollama
sudo systemctl status ollama --no-pager
~~~

APIの応答を確認する。

~~~bash
curl -fsS http://127.0.0.1:11434/api/tags
~~~

## モデルの取得

予定モデルは `gemma4:31b` とする。

~~~bash
ollama pull gemma4:31b
ollama list
~~~

モデルをQwenへ変更する場合の例：

~~~bash
ollama pull qwen3:32b
~~~

## Ollama本体のアップデート

Linuxでは、公式インストールスクリプトを再実行する。

~~~bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl daemon-reload
sudo systemctl restart ollama
~~~

更新後にバージョンとサービスを確認する。

~~~bash
ollama --version
sudo systemctl status ollama --no-pager
curl -fsS http://127.0.0.1:11434/api/tags
~~~

Ollama本体のアップデートとモデルの更新は別である。モデルも更新したい場合は、別途 `ollama pull` を実行する。

~~~bash
ollama pull gemma4:31b
ollama list
ollama ps
~~~

## Debate APIの確認

Ollamaの更新後、Debate APIが起動していることを確認する。

~~~bash
sudo systemctl status debate-api --no-pager
curl -fsS http://127.0.0.1:8000/health
~~~

Debate APIの再起動が必要な場合：

~~~bash
sudo systemctl restart debate-api
~~~

## tmuxについて

systemdサービスとして起動するため、サーバー運用でtmuxは必要ない。

tmuxが必要なのは、開発時に手動で `ollama serve` を実行する場合だけである。

## ログ確認

~~~bash
sudo journalctl -u ollama -n 100 --no-pager
sudo journalctl -u debate-api -n 100 --no-pager
~~~

## 公式ドキュメント

- [Ollama Linux](https://docs.ollama.com/linux)
- [Ollama FAQ](https://docs.ollama.com/faq)
- [Ollama Chat API](https://docs.ollama.com/api/chat)
