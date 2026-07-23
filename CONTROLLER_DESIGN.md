# Debate Controller設計

## 1. 設計目標

初版では通常のPythonステートマシンを使用する。ただし、将来LangGraphを導入しても、次の部分を変更しない設計にする。

- ブラウザ向けAPI
- SSEイベント形式
- ディベート状態の意味
- Ollama Clientの接続インターフェース
- 発言履歴の形式
- stop、reset、errorの扱い

LangGraphは、Controller全体を置き換えるのではなく、ターン進行を実行するRunnerとして追加する。

## 2. レイヤー構成

```text
HTTP / SSE
    │
    ▼
DebateController       安定したユースケース境界
    │
    ▼
DebateRunner           実行エンジンの抽象
    ├─ PythonRunner     初版
    └─ LangGraphRunner  将来追加
    │
    ├─ Domain State
    ├─ Domain Transitions
    └─ Ports
         ├─ LLMPort
         ├─ SessionRepository
         └─ EventPublisher
    │
    ▼
Infrastructure
    ├─ OllamaClient
    └─ InMemorySessionRepository
```

### 依存方向

- DomainはFastAPI、Ollama、LangGraphをimportしない。
- DebateControllerはHTTPのRequestやResponseを扱わない。
- SSE変換はAPI層で行う。
- OllamaのHTTP形式はOllamaClient内に閉じ込める。
- LangGraph固有のStateGraphやCheckpointerはLangGraphRunner内に閉じ込める。

## 3. 推奨ディレクトリ

```text
server/app/
├── main.py
├── config.py
├── domain/
│   ├── state.py
│   ├── theme_context.py
│   ├── turn_plan.py
│   ├── transitions.py
│   └── events.py
├── application/
│   ├── debate_controller.py
│   ├── debate_runner.py
│   ├── theme_context.py
│   ├── prompts.py
│   └── ports.py
├── infrastructure/
│   ├── ollama_client.py
│   └── session_store.py
└── api/
    └── debates.py
```

将来のLangGraph実装：

```text
server/app/application/runners/
├── python_runner.py
└── langgraph_runner.py
```

初版ではpython_runner.pyだけを実装する。

## 4. 状態モデル

LangGraphへ渡せるよう、状態はJSONへシリアライズ可能なデータだけで構成する。

```json
{
  "debate_id": "uuid",
  "theme": "大学の授業で生成AIの使用を認めるべきである",
  "theme_context": {
    "version": "v1",
    "raw_theme": "大学の授業で生成AIの使用を認めるべきである",
    "motion": "大学の授業では生成AI利用を認めるべきか",
    "definitions": [],
    "scope": "大学の授業を対象とする",
    "assumptions": [],
    "evaluation_axes": ["学習効果", "公平性", "実施可能性"],
    "clarification_needed": false
  },
  "model": "gemma4:31b",
  "state": "waiting",
  "turn_index": 3,
  "current_speaker": null,
  "current_kind": null,
  "messages": [
    {
      "message_id": "uuid",
      "speaker": "A",
      "turn_index": 1,
      "kind": "opening",
      "text": "発言本文",
      "status": "completed"
    }
  ],
  "error": null
}
```

状態に含めるもの：

- テーマ
- ThemeContext
- モデル名
- 現在の状態
- ターン番号
- 現在の話者
- 発言履歴
- エラー情報

状態に含めないもの：

- asyncio.Lock
- HTTP接続
- OllamaのResponseオブジェクト
- SSEのストリーム
- FastAPIのRequest、Response
- 認証情報
- ログ出力用オブジェクト

これらはRuntime ContextまたはInfrastructure層で管理する。

## 5. Domainの純粋な処理

Domain層には外部I/Oを持たせない。

### turn_plan.py

固定10ターンを定義する。

```python
TURN_PLAN = [
    ("C", "define"),
    ("A", "opening"),
    ("B", "opening"),
    ("C", "organize"),
    ("A", "rebuttal"),
    ("B", "rebuttal"),
    ("C", "reconcile"),
    ("A", "closing"),
    ("B", "closing"),
    ("C", "summary"),
]
```

### transitions.py

状態を受け取り、新しい状態またはCommandを返す純粋関数を定義する。

```text
prepare_turn(state)
  → 次の話者、ターン種別、生成用コンテキスト

complete_turn(state, generated_text)
  → 発言履歴を追加し、Turn 1ならThemeContextを確定した新しい状態

stop_turn(state, partial_text)
  → stopped発言を追加したwaiting状態

reset_debate(state)
  → ready状態の初期状態

fail_turn(state, error)
  → error状態
```

これらの関数はOllamaを呼び出さない。LangGraph導入後は、これらの関数をGraph node内から呼び出せる。

## 6. DebateControllerの責務

DebateControllerはAPIから呼ばれる安定したユースケース境界とする。

責務：

- セッションを取得する
- セッション単位の排他制御を行う
- サーバー全体で1件だけLLM生成を許可する
- 現在の状態を検証する
- 選択されたDebateRunnerを呼び出す
- Domain EventをAPI層へ返す
- セッションスナップショットを保存する

責務に含めないもの：

- FastAPIのSSE実装
- OllamaのHTTPリクエスト作成
- ターン順の直接記述
- LangGraphのGraph構築
- HTMLの生成

生成中にセッションロックを保持し続けない。生成開始時にactive runを登録してロックを解放し、stopは別の短い状態更新として即時にキャンセル要求を設定する。

### generation_manager.py

サーバー全体のLLM実行枠を管理する。

- 同時に1件だけ生成を許可する
- 待ち行列を作らず、使用中ならnextを429で拒否する
- active runとキャンセルイベントを保持する
- stopから生成タスクへ即時にキャンセル要求を伝える
- 生成終了時に必ず実行枠を解放する

## 7. DebateRunnerのインターフェース

初版と将来実装を同じインターフェースで扱う。

```python
class DebateRunner(Protocol):
    async def advance(
        self,
        state: DebateState,
        runtime: RuntimeContext,
    ) -> AsyncIterator[DomainEvent]:
        ...

    async def stop(
        self,
        state: DebateState,
        runtime: RuntimeContext,
    ) -> AsyncIterator[DomainEvent]:
        ...

    def reset(self, state: DebateState) -> DebateState:
        ...
```

実装：

```text
PythonRunner
  - transitions.pyを順番に呼ぶ
  - OllamaPortで生成する
  - DomainEventを発行する

LangGraphRunner
  - DebateStateをGraph Stateとして使用する
  - nodeからtransitions.pyを呼ぶ
  - 同じOllamaPortで生成する
  - Graphのstream eventをDomainEventへ変換する
```

API層はRunnerの種類を意識しない。

## 8. Portの設計

### LLMPort

```python
class LLMPort(Protocol):
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        num_ctx: int,
    ) -> AsyncIterator[str]:
        ...
```

OllamaのHTTP実装はOllamaClientが担当する。LangGraphRunnerからも同じLLMPortを利用する。

### SessionRepository

```python
class SessionRepository(Protocol):
    async def get(self, debate_id: str) -> DebateState | None:
        ...

    async def save(self, state: DebateState) -> None:
        ...
```

初版はInMemorySessionRepositoryとする。将来はSQLite、Redis、LangGraph Checkpointerなどへ差し替えられる。

### EventPublisher

```python
class EventPublisher(Protocol):
    async def publish(self, event: DomainEvent) -> None:
        ...
```

初版はControllerまたはRunnerがAsyncIteratorでイベントを返し、API層がGETのSSE接続へ変換する。EventPublisherは複数購読者が必要になった段階で追加する。重要なのは、Domain Event自体にSSE固有の形式を持たせないことである。

## 9. Domain Event

RunnerからAPI層へ渡すイベントをフレームワーク非依存にする。

```text
turn_started
token
turn_completed
turn_stopped
theme_context_ready
theme_clarification_required
debate_finished
debate_error
```

イベント例：

```json
{
  "type": "token",
  "debate_id": "uuid",
  "turn_index": 1,
  "speaker": "A",
  "text": "生成された"
}
```

API層では次のように変換する。

```text
DomainEvent.type = token
  → SSE event: token
  → JSON data: DomainEvent.payload
```

LangGraphのstream出力を採用しても、ブラウザへ送るSSE契約は変更しない。

## 10. 現在のPythonRunnerの処理単位

一つのnext要求を、次の段階に分ける。

```text
1. load_state
2. prepare_turn
3. build_prompt
4. generate_tokens
5. complete_turn
6. extract_theme_context_if_define_turn
7. save_state
8. emit_turn_completed
9. emit_theme_context_event_if_needed
10. route_next_or_finished
```

各段階を別関数にする。特にprepare_turn、complete_turn、route_next_or_finishedは純粋なDomain処理として実装する。

この分割により、将来のLangGraphでは次のNodeへ対応付けられる。

```text
prepare_turn       → prepare_turn node
build_prompt       → build_prompt node
generate_tokens    → generate_turn node
complete_turn      → complete_turn node
extract_theme_context → extract_theme_context node
route_next         → conditional edge
```

## 11. stopとキャンセル

停止処理は、Pythonのasyncio.CancelledErrorだけに依存しない。

Runtime Contextに次を持たせる。

```python
class RuntimeContext:
    cancellation_requested: asyncio.Event
    active_task: asyncio.Task | None
```

- stop要求でcancellation_requested.set()を呼ぶ。
- Ollamaストリームをキャンセルする。
- 受信済みの部分テキストをstopped状態として保存する。
- APIにはturn_stoppedイベントを送る。
- LangGraph導入後も、Graph外のRuntime Contextで停止要求を管理する。

## 12. LangGraphへの移行手順

1. PythonRunnerを完成させる。
2. Domain StateとDomain Eventのテストを完成させる。
3. DebateRunnerインターフェースを固定する。
4. LangGraphRunnerを追加する。
5. DebateStateをGraph Stateとして登録する。
6. PythonRunnerの各段階をGraph nodeへ対応付ける。
7. conditional edgeで次ターンと終了を表現する。
8. LangGraphのstream eventをDomain Eventへ変換する。
9. 同じAPIテストをPythonRunnerとLangGraphRunnerの両方へ実行する。
10. 実機で安定性を比較する。

切り替え方法は設定値で行う。

```text
DEBATE_ENGINE=python
DEBATE_ENGINE=langgraph
```

API層とフロントエンドはこの設定を知らない。

## 13. LangGraph導入時に追加するもの

- LangGraph依存関係
- LangGraphRunner
- Graph State変換
- Node定義
- conditional edge
- Checkpointer
- Graph実行ログ
- LangGraph固有の単体テスト

既存のOllamaClient、API、SSEイベント、Domain Stateの意味は維持する。

## 14. 設計上の禁止事項

- ControllerからLangGraphのGraph Stateへ直接依存する
- OllamaのJSONチャンクをSSEとしてそのまま返す
- FastAPIのResponseをDomain層へ渡す
- asyncio.LockをDebateStateへ保存する
- APIリクエストごとにGraphを構築する
- ターン順をLLMまたはGraphの自動判断だけに任せる
- LangGraph導入を理由にAPI契約を変更する
