# サーバー側実装計画

> 2026-07-22改訂：ネットワーク層はTailscale固定ではなく、TailscaleまたはNetBirdを選択可能とする。Debate API、SSE、コントローラ、Ollamaのlocalhost境界は共通で、差分はUbuntuセットアップ時のオーバーレイクライアントと公開方法だけに限定する。実装済みの入口は `server/scripts/setup_ubuntu.sh` である。

## 1. 目的

Ubuntu上のOllamaと接続し、ブラウザから手動進行できるローカルLLMディベートのバックエンドを実装する。

初版で実現する機能：

- テーマの受付
- 生テーマの正規化とThemeContextの生成
- A・B・Cの発言順のサーバー側管理
- Ollamaへの1ターンずつの問い合わせ
- 生成中テキストのブラウザへのストリーミング
- セッション状態と発言履歴の管理
- 停止、リセット、エラー処理

## 2. 採用構成

```text
ブラウザ
  │ HTTPS / Tailscale Serve または Overlay IP
  ▼
FastAPI
  ├─ Debate API
  ├─ Debate Controller
  ├─ Session Store（初版はメモリ）
  └─ Ollama Client
       │ http://127.0.0.1:11434
       ▼
     Ollama
       └─ gemma4:31b
```

- WebフレームワークはFastAPI。
- Debate ControllerはFastAPIプロセス内のPythonモジュール。
- 発言順と終了条件は固定のPythonデータ構造で管理する。
- OllamaへのHTTP通信はOllama Clientに分離する。
- ブラウザへの発言配信はSSEを使用する。
- 初版のセッション保存先はメモリとする。
- OllamaとDebate APIは同じUbuntuサーバーで動かす。
- Ollamaは127.0.0.1:11434に限定する。
- モデルはgemma4:31bを予定する。

### LangGraphの扱い

初版の実行エンジンは通常のPythonステートマシンとする。ただし、Controller全体をLangGraphへ直接依存させず、DebateRunnerという実行エンジン境界を設ける。

初版はPythonRunnerを使用し、将来は同じDebateRunnerインターフェースにLangGraphRunnerを追加する。API、SSEイベント、Domain State、Ollama Clientは変更しない。

詳細は [CONTROLLER_DESIGN.md](CONTROLLER_DESIGN.md) に定義する。

## 3. 固定するディベート進行

```python
TURN_PLAN = [
    ("C", "define"),
    ("A", "opening"),
    ("B", "opening"),
    ("C", "organize"),
    ("A", "rebuttal"),
    ("B", "rebuttal"),
    ("A", "closing"),
    ("B", "closing"),
    ("C", "summary"),
]
```

turn_indexは次に実行するターンを指す。

- 0：まだ発言していない
- 9：全ターン完了
- 発言順をLLMに決めさせない
- generating中は同じセッションの次ターンを開始しない

## 4. ディレクトリ構成案

```text
Debate/
├── SPEC.md
├── OLLAMA_SERVER_SETUP.md
├── SERVER_SETUP_SCRIPT_PLAN.md
├── SERVER_IMPLEMENTATION_PLAN.md
├── CONTROLLER_DESIGN.md
├── CLIENT_DESIGN.md
├── BROWSER_UI_DESIGN.md
├── PROMPT_SPEC.md
└── server/
    ├── scripts/
    │   ├── common.sh
    │   ├── 00_check_prerequisites.sh
    │   ├── 10_install_ollama.sh
    │   ├── 20_configure_ollama.sh
    │   ├── 30_pull_model.sh
    │   ├── 40_install_tailscale.sh
    │   ├── 50_verify_ollama.sh
    │   ├── 60_verify_tailscale.sh
    │   └── setup_server.sh
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── config.py
    │   ├── static/
    │   │   ├── index.html
    │   │   ├── styles.css
    │   │   └── app.js
    │   ├── domain/
    │   │   ├── state.py
    │   │   ├── theme_context.py
    │   │   ├── turn_plan.py
    │   │   ├── transitions.py
    │   │   └── events.py
    │   ├── application/
    │   │   ├── debate_controller.py
    │   │   ├── debate_runner.py
    │   │   ├── generation_manager.py
    │   │   ├── theme_context.py
    │   │   ├── prompts.py
    │   │   └── ports.py
    │   ├── infrastructure/
    │   │   ├── ollama_client.py
    │   │   └── session_store.py
    │   └── api/
    │       └── debates.py
    ├── tests/
    │   ├── test_domain_transitions.py
    │   ├── test_controller.py
    │   ├── test_ollama_client.py
    │   └── test_api.py
    ├── requirements.txt
    ├── .env.example
    └── README.md
```

## 5. 主要コンポーネント

### config.py

環境変数を読み込む。

```text
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma4:31b
DEBATE_MAX_CHARS=300
DEBATE_NUM_CTX=32768
OLLAMA_TIMEOUT_SECONDS=180
```

モデル名はブラウザから変更させない。初版のコンテキスト長は32768を初期値とし、RTX A6000 48GBで実測後に必要ならOLLAMA_NUM_CTXで調整する。

### domain/state.py

APIと内部状態で使用するデータ構造を定義する。LangGraphへ渡せるよう、Domain StateはJSONへシリアライズ可能なデータだけで構成する。排他ロックやHTTP接続は状態に含めない。

セッションには少なくとも次を保持する。

```text
debate_id
theme
theme_context
model
state
turn_index
messages
current_speaker
current_turn
error_message
created_at
updated_at
```

発言には少なくとも次を保持する。

```text
message_id
speaker
turn_index
kind
text
status
started_at
completed_at
```

### application/debate_controller.py

Debate Controllerは、APIから呼ばれる安定したユースケース境界とする。

- セッションの取得と保存
- テーマと現在状態の検証
- セッション単位の排他制御
- サーバー全体のLLM実行枠の確保
- DebateRunnerの呼び出し
- Domain Eventの受け渡し
- リセット

ControllerはFastAPI、Ollama、LangGraphの詳細を直接扱わない。ターン進行の実装はDebateRunnerへ委譲する。

### application/debate_runner.py

実行エンジンのインターフェースを定義する。初版はPythonRunner、将来はLangGraphRunnerを実装する。

- PythonRunner：固定ターンを通常のPython処理で実行
- LangGraphRunner：同じStateとEventを使ってGraphで実行

### domain/

状態、ターン定義、状態遷移、Domain Eventを配置する。外部I/Oを持たせない。

### application/ports.py

LLMPort、SessionRepository、EventPublisherなどの抽象インターフェースを定義する。OllamaやSQLiteなどの具体的な実装はinfrastructure側に置く。

### application/prompts.py

A、B、Cそれぞれの固定system promptとターン別指示を管理する。テーマをsystem promptへ埋め込まず、Turn 1後のThemeContextをuser promptへ差し込む。

具体的なプロンプト、履歴形式、出力検証は [PROMPT_SPEC.md](PROMPT_SPEC.md) に従う。PROMPT_VERSIONを付け、プロンプト変更を追跡できるようにする。

共通制約：

- 日本語で回答する
- 最大300文字程度
- 相手や個人を攻撃しない
- 事実と推測を区別する
- 指定されたターンの目的にだけ回答する
- Cは賛否を表明しない

Aには賛成の根拠とBの主張への応答を求める。Bには反対の根拠と代替案または条件を求める。Cには公平な整理と次の論点の提示を求める。

Turn 1では生テーマをCへ引用付きで渡し、Cの出力からThemeContextを作る。Turn 2以降はThemeContextと直前までの発言履歴を渡す。

### application/theme_context.py

Turn 1のC出力からThemeContextを作成する。

- `議題（整理後）`、`用語の定義`、`対象範囲・前提`、`主な評価観点`をラベルで抽出する。
- 抽出結果をPydanticまたはdataclassのJSONシリアライズ可能な値に変換する。
- 「議論可能な形に整理できない」と判断された場合は`clarification_needed=true`にする。
- ラベル抽出に失敗した場合は、PROMPT_SPEC.mdのフォールバック値を使う。
- Turn 1完了後にThemeContextを固定し、A・Bのターンでは書き換えない。

このモジュールはLLMを直接呼び出さない。Cの生成結果を解釈するだけにし、LLM呼び出しは既存のLLMPortへ集約する。

### infrastructure/ollama_client.py

Ollamaの /api/chat を呼び出す。

- modelは設定値のgemma4:31bを使う。
- stream: trueでチャンクを受け取る。
- チャンクからテキストを取り出し、Controllerへ渡す。
- タイムアウトを設定する。
- HTTPエラーとJSON解析エラーをアプリケーション例外へ変換する。
- 停止要求を受けた場合はHTTPリクエストをキャンセルする。

Ollamaのストリーミング形式と、ブラウザ向けSSE形式をこのモジュールの外で混在させない。

### infrastructure/session_store.py

初版はプロセス内の辞書で管理する。

```python
sessions: dict[str, DebateSession]
```

- debate_idでセッションを検索する。
- セッションごとにasyncio.Lockを持つ。
- サーバー再起動時にセッションが消えることは初版の仕様とする。
- 永続DBは、基本動作確認後に必要性を判断する。

## 6. API実装

### GET /health

サーバーの稼働確認。

```json
{
  "status": "ok"
}
```

### POST /api/debates

新しいディベートを作成する。

```json
{
  "theme": "大学の授業で生成AIの使用を認めるべきである"
}
```

処理：

1. テーマが空でないことを確認する。
2. debate_idを発行する。
3. ready状態のセッションを作成する。
4. モデル名をサーバー設定から付与する。

### GET /api/debates/{debate_id}

画面再読み込みや状態確認に使用する。

返す情報：

- テーマ
- ThemeContext
- モデル名
- 現在の状態
- 現在のターン
- 次の話者
- 発言履歴
- エラー情報

### POST /api/debates/{debate_id}/next

次のターンの生成を開始する。生成結果はこのレスポンスでは返さず、SSE接続へ送る。

処理：

1. セッションを取得する。
2. セッションがgenerating、stopping、clarifyingでないことを確認する。
3. finishedでないことを確認する。
4. サーバー全体のLLM実行枠が空いていることを確認する。
5. TURN_PLANから次の話者とターン種別を決める。
6. 状態をgeneratingにする。
7. バックグラウンドの生成タスクを登録する。
8. `202 Accepted` を返す。

エラー：

- 同じセッションが実行中なら `409 Conflict`
- 別セッションがLLMを使用中なら `429 Too Many Requests`

### GET /api/debates/{debate_id}/events

セッション単位のSSEイベントを購読する。クライアントは最初のnextより先に接続する。

生成タスクから受け取ったDomain EventをSSEへ変換する。

SSEイベント例：

```text
event: turn_started
data: {"speaker":"A","turn_index":1,"kind":"opening"}

event: token
data: {"text":"生成された"}

event: token
data: {"text":"発言"}

event: turn_completed
data: {"speaker":"A","turn_index":1,"state":"waiting"}
```

各イベントにSSEの `id` を付ける。接続断時の再接続では、まず状態取得APIで最新状態を確認する。

Turn 1が完了した場合は、`theme_context_ready`または`theme_clarification_required`を`turn_completed`と併せて送る。

### POST /api/debates/{debate_id}/theme

`clarifying`中、またはTurn 1のやり直し時にテーマを修正する。ThemeContext、発言履歴、turn_indexを初期化し、`ready`へ戻す。生成中は受け付けない。

### POST /api/debates/{debate_id}/stop

現在の生成を停止する。生成ロックを待たず、停止要求を即時に受け付ける。

初版の扱い：

- 状態をstoppingにする。
- active generationへキャンセル要求を設定する。
- `202 Accepted` を返す。
- Ollamaへのストリームをキャンセルする。
- 生成途中のテキストはstopped状態の発言として保持する。
- stateはwaitingに戻す。
- 終了後に `turn_stopped` イベントを送る。
- `turn_stopped` を受け取るまで次の発言を開始できない。

### POST /api/debates/{debate_id}/reset

セッションを初期状態へ戻す。

- 発言履歴を空にする。
- turn_indexを0に戻す。
- stateをreadyに戻す。
- 生成中の場合は先にキャンセルする。

## 7. 状態遷移

```text
idle
  │ テーマ作成
  ▼
ready
  │ next
  ▼
generating
  ├─ 正常終了 ──▶ waiting ──▶ next
  ├─ Turn 1で整理不能 ──▶ clarifying ──▶ theme修正 ──▶ ready
  ├─ 最終ターン終了 ──▶ finished
  ├─ stop ──▶ waiting
  └─ エラー ──▶ error
```

- idleからreadyへの遷移はセッション作成時に行う。
- generating中にnextを受けた場合は処理しない。
- errorの詳細はログへ記録する。
- リセットはreadyへ戻す。

## 8. 実装フェーズ

### Phase 0：サーバー環境確認

セットアップ手順は [SERVER_SETUP_SCRIPT_PLAN.md](SERVER_SETUP_SCRIPT_PLAN.md) に従い、Ubuntu上でスクリプト化する。Tailscaleの認証だけは自動化せず、利用者が `tailscale up` を実行する。

対象：

- Ubuntu
- Ollama
- gemma4:31b
- 127.0.0.1:11434
- TailscaleまたはNetBird

完了条件：

- curl http://127.0.0.1:11434/api/tagsが応答する。
- gemma4:31bが取得済みである。
- ollama psで推論状態を確認できる。

### Phase 1：FastAPIの最小起動

実装：

- server/のPython環境
- requirements.txt
- main.py
- GET /health

完了条件：

- FastAPIがlocalhostで起動する。
- /healthがJSONを返す。
- 設定値を環境変数から読み込める。

### Phase 2：Ollama Client

実装：

- /api/chatの非ストリーミング呼び出し
- ストリーミング呼び出し
- タイムアウト
- エラー変換
- モデル名とコンテキスト長の設定

完了条件：

- 実際のgemma4:31bへ問い合わせできる。
- 応答テキストを取得できる。
- Ollama停止時に明確な例外となる。

### Phase 3：Debate Controller

実装：

- Domain StateとTURN_PLAN
- Domainの状態遷移関数
- DebateControllerのユースケース境界
- DebateRunnerインターフェース
- PythonRunner
- generation_manager.pyによるサーバー全体の同時実行数1制御
- 発言履歴
- セッション単位のロック
- ThemeContextの生成・固定・フォールバック
- プロンプト生成

完了条件：

- 9ターンが順番どおりに進む。
- A、B、Cの話者が入れ替わらない。
- 10ターン目を実行できない。
- テーマごとにThemeContextの議題・範囲・評価観点が変わる。
- Turn 1のThemeContextが確定するまでA・Bを実行しない。
- 生成中の二重実行を拒否できる。
- 別セッション実行中の429応答が返る。
- stopが生成ロックを待たずに受理される。

### Phase 4：APIとSSE

実装：

- セッション作成API
- 状態取得API
- 次ターン開始API（202 Accepted）
- テーマ修正API
- GETイベント購読API
- 停止API
- リセットAPI
- SSEイベント

完了条件：

- curlまたは簡単なテストクライアントで、1ターンのストリーミングを確認できる。
- turn_started、token、turn_completedが順番に届く。
- Turn 1でtheme_context_readyまたはtheme_clarification_requiredが届く。
- エラーがSSEまたはHTTPエラーとして通知される。

### Phase 5：実機統合テスト

実装：

- Ollama実機との接続確認
- gemma4:31bの応答時間確認
- GPU/CPU配置確認
- 停止処理確認
- Tailscale経由のAPIアクセス確認

完了条件：

- Tailscale内のクライアントからAPIへ接続できる。
- 9ターンを最後まで実行できる。
- 生成中の停止とリセットが機能する。
- サーバーログから障害原因を追跡できる。

## 9. テスト計画

### 単体テスト

- TURN_PLANの話者順
- ターン番号の増加
- 状態遷移
- テーマの空入力拒否
- ThemeContextのラベル抽出
- テーマ別のプロンプト差し替え
- 曖昧テーマのclarifying遷移
- 文字数制約のプロンプト
- A・B・Cのシステムプロンプト
- 完了後の追加実行拒否
- セッション不在時の404
- 生成中の二重実行拒否

### Ollama Clientテスト

- 正常なストリーミング
- Ollamaの接続拒否
- タイムアウト
- 不正なJSONチャンク
- モデル未取得エラー

### APIテスト

- /health
- セッション作成
- 状態取得
- SSEイベントの順番
- SSEイベントのid
- GETイベント接続の切断・再接続
- stop
- reset
- 生成中のstopとturn_stoppedイベント
- 別セッションの同時実行拒否
- 409、404、422、500のエラー応答

### 実機確認

実際のUbuntuサーバー上で次を確認する。

- gemma4:31bの初回ロード時間
- 1ターンあたりの生成時間
- GPUメモリ使用量
- 連続9ターン時の安定性
- 停止後にOllamaプロセスが残らないこと

## 10. 初版で作らないもの

- LangGraphの実装（初版はPythonRunner）
- Reactなどの画面実装
- 論点マップ
- 自動進行
- 聴衆質問
- 勝敗判定・採点
- 永続データベース
- 複数ユーザーの同時参加
- 複数モデルの同時実行
- アプリケーション独自のログイン機能

Tailnetへの参加制御はTailscale側で行い、アプリケーション認証は必要性を確認してから追加する。

## 11. 実装開始条件

次の条件がそろったら、Phase 1の実装を開始する。

- [ ] OLLAMA_SERVER_SETUP.mdのセットアップをUbuntu上で完了した
- [ ] gemma4:31bのCLI応答を確認した
- [ ] /api/chatのHTTP応答を確認した
- [ ] ollama psでGPU/CPU配置を確認した
- [ ] Debate APIを動かすローカルポートを決めた
- [ ] サーバー上のPythonバージョンを決めた
- [ ] Tailscaleのサーバー名を決めた

## 12. 実装完了の最低条件

- GET /healthが動作する。
- テーマからセッションを作成できる。
- nextで9ターンを順番に実行できる。
- Ollamaの生成結果をSSEで受け取れる。
- 発言履歴を取得できる。
- stopとresetが動作する。
- Ollama停止時にエラーを通知できる。
- Tailscale内のクライアントからDebate APIへ接続できる。
