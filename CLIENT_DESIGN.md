# クライアント側設計

## 1. 目的

ノートPCからTailscale、NetBird、またはSSHトンネル経由でDebate APIへ接続し、ディベートの状態と発言を分かりやすく表示する。

クライアントは次の2種類を想定する。

1. ブラウザ
2. 専用アプリ

初版はブラウザを第一候補とする。専用アプリを後から追加しても、サーバーAPIとSSEイベント形式は変更しない。

初版ブラウザ画面の具体的なレイアウト、配色、状態表示は [BROWSER_UI_DESIGN.md](BROWSER_UI_DESIGN.md) に定義する。

## 2. 全体構成

```text
ノートPC
  ├─ Tailscale または NetBird Client
  └─ ブラウザ（初版）
       │ HTTPS / Tailnet
       ▼
Ubuntuサーバー
  ├─ Tailscale Serve（任意）
  └─ Debate API
       │ localhost
       ▼
     Ollama
```

重要な境界：

- ノートPCはOllamaへ直接接続しない。
- ノートPCは11434番ポートへ接続しない。
- クライアントが接続するのはDebate APIだけ。
- ディベートのターン順、状態、LLM同時実行制御はサーバーが決める。
- クライアントはサーバーの状態を表示し、操作要求を送るだけにする。

## 3. ブラウザを第一候補とする理由

初版はブラウザを採用する。

- ノートPCへのインストールが不要
- Tailscale ServeのHTTPS URLを開くだけで利用できる
- EventSourceによるGETのSSEをそのまま利用できる
- 画面の修正と再配布が容易
- 専用アプリと同じREST APIを利用できる
- デモ時に別のノートPCへ切り替えやすい

専用アプリは、次の要求が出た場合に追加する。

- OS通知や常駐表示が必要
- ブラウザのタブ管理を避けたい
- ウィンドウサイズやショートカットを固定したい
- オフライン時の設定保存が必要
- 発表者向けの専用操作を追加したい

## 4. オーバーレイネットワーク経由の接続

初版の通信契約はTailscaleとNetBirdで共通にする。クライアントはDebate APIのURLだけを持ち、OllamaのURLやオーバーレイ固有のAPIを持たない。

| 方式 | サーバー側の入口 | クライアントURL |
|---|---|---|
| Tailscale Serve | localhostの8000番をServeでHTTPS公開 | TailscaleのHTTPS URL |
| Tailscale直接 | オーバーレイIPの8000番 | Tailscale IPのHTTP URL |
| NetBird直接 | NetBird IPの8000番 | NetBird IPのHTTP URL |
| SSHトンネル | SSH転送先のlocalhost:8000 | http://127.0.0.1:8000 |

Tailscale Serveを使う場合はHTTPSを優先する。直接接続方式を使う場合は、TCP 8000番をオーバーレイ側ポリシーとホスト側ファイアウォールで制限する。

SSHトンネル方式では、サーバーのDebate APIを127.0.0.1だけで待ち受けさせ、ノートPCから次の転送を行う。

~~~bash
ssh -N -L 8000:127.0.0.1:8000 ubuntu@<server-host>
~~~

### 4.1 接続先

クライアントはTailscaleのMagicDNS名でDebate APIへ接続する。

```text
https://<debate-server>.<tailnet>.ts.net/
```

実際のホスト名はサーバー登録後に決定する。Tailscale IPを直接使うこともできるが、初版はMagicDNS名を優先する。

### 4.2 通信条件

- ノートPCとUbuntuサーバーが同じTailnetに参加していること。
- Tailnet ACLでノートPCからDebate APIへのアクセスを許可すること。
- Tailscale ServeでDebate APIのlocalhostポートをHTTPS公開すること。
- インターネットへポートフォワーディングしないこと。
- クライアントにOllamaのURLを設定しないこと。
- 本番画面はDebate APIと同じオリジンから配信すること。

同一オリジンで配信することで、初版ではブラウザ側のCORS設定を不要にする。

## 5. 通信フロー

### 5.1 初期表示

1. ブラウザでDebate画面を開く。
2. GET /healthで接続状態を確認する。
3. 接続成功後、テーマ入力を有効にする。
4. 接続失敗時はサーバーURL、Tailnet接続、サーバー状態を確認する案内を表示する。

### 5.2 ディベート開始

1. POST /api/debatesでテーマを送る。
2. debate_idを受け取る。
3. GET /api/debates/{debate_id}/eventsを開始する。
4. GET /api/debates/{debate_id}で初期状態を取得する。
5. 「次の発言」を有効にする。

Turn 1のCが完了すると、`theme_context_ready`を受けて整理後の議題、評価観点、仮定を画面へ表示する。`theme_clarification_required`を受けた場合は、A・Bの生成へ進まず、テーマ修正操作を表示する。

SSE接続は、最初のnext要求より前に開く。これにより、生成開始直後のturn_startedイベントを取りこぼさない。

### 5.3 次の発言

1. クライアントがボタンを押す。
2. クライアントはボタンを即時無効化する。
3. POST /api/debates/{debate_id}/nextを送る。
4. 202 Acceptedを受け取る。
5. SSEのtokenイベントを受け取り、該当パネルへ追記する。
6. turn_completedを受け取ったら発言履歴を確定する。
7. 次の発言ボタンを有効にする。

別のセッションがLLMを使用中の場合は429を受け取る。クライアントは自動再送せず、サーバーが空くまで待つ。

### 5.4 停止

1. クライアントが停止ボタンを押す。
2. 停止ボタンと次の発言ボタンを無効にする。
3. POST /api/debates/{debate_id}/stopを送る。
4. 202 Acceptedを受け取る。
5. 状態を停止中として表示する。
6. turn_stoppedイベントを受け取る。
7. サーバーから返された状態を表示し、次の発言またはリセットを有効にする。

停止要求のHTTP応答を待つ間も、クライアント側の表示は停止中へ変更する。

### 5.5 再接続

SSE接続が切れた場合：

1. 接続状態を再接続中にする。
2. GET /api/debates/{debate_id}で最新状態を取得する。
3. EventSourceを再接続する。
4. 生成中なら、現在の発言表示をサーバー状態と照合する。
5. 次の発言ボタンは、状態がwaitingまたはreadyになるまで有効にしない。

初版では、イベントを完全再送するよりも、再接続後に状態取得APIで画面を再同期する。

## 6. クライアント状態

クライアントはサーバー状態を表示用に変換する。

```text
disconnected
  │ health成功
  ▼
connected
  │ debate作成
  ▼
ready
  │ next 202
  ▼
generating
  ├─ turn_completed ──▶ waiting
  ├─ stop受付 ────────▶ stopping
  ├─ turn_stopped ────▶ waiting
  ├─ theme_clarification_required ─▶ clarifying
  └─ error ───────────▶ error
waiting
  │ 最終ターン完了
  ▼
finished

clarifying
  │ theme修正
  ▼
ready
```

表示用の状態：

- 接続確認中
- 接続済み
- テーマ入力待ち
- 次の発言待ち
- テーマ確認待ち
- A/B/Cが生成中
- 停止処理中
- サーバーが使用中
- 完了
- エラー
- 再接続中

クライアントは状態を独自に進めない。サーバーから受け取った状態とイベントを表示する。

## 7. クライアント内データ

最小限、次を保持する。

```text
serverUrl
debateId
theme
themeContext
serverState
turnIndex
currentSpeaker
currentDraftText
messages
sseConnectionState
lastEventId
error
```

- serverStateはサーバーの状態をそのまま保持する。
- currentDraftTextは生成中の一時表示に使う。
- turn_completedを受け取ったらcurrentDraftTextをmessagesへ確定する。
- lastEventIdはSSE再接続拡張用に保持する。
- Ollamaのモデル内部状態はクライアントに保持しない。

## 8. 画面構成

### ヘッダー

- アプリ名
- サーバー接続状態
- サーバー名
- 現在のターン番号
- モデル名
- Tailnet経由で接続している旨

### テーマ領域

- テーマ入力欄
- テーマ確定または開始ボタン
- テーマ確定後は生成中に編集不可

### 発言領域

3列を基本とする。

- A：青系、賛成側
- B：赤系、反対側
- C：中立色、ファシリテーター

各パネルに表示するもの：

- 話者名と役割
- 生成中表示
- 最新発言
- 生成完了状態
- 停止済み状態

### 操作領域

- 次の発言
- 停止
- リセット
- 再接続
- 発言履歴の表示切替

操作制御：

- readyまたはwaitingだけで次の発言を有効にする。
- generatingまたはstoppingでは次の発言を無効にする。
- 最終ターン後は次の発言を無効にする。
- 429の場合はサーバー使用中と表示する。
- 409の場合は最新状態を取得して画面を同期する。

### 発言履歴

- 話者
- ターン番号
- 発言種別
- 発言本文
- 完了、停止、エラーの状態

停止した部分発言は表示してもよいが、正式な完了発言とは視覚的に区別する。

## 9. ブラウザ実装方針

初版では、Debate APIと同じサーバーから静的ファイルを配信する。

構成例：

```text
server/app/static/
├── index.html
├── styles.css
└── app.js
```

- API呼び出しはfetchを使用する。
- SSEはGETのEventSourceを使用する。
- 接続先は相対URLを基本とする。
- UIはサーバーのJSON状態を唯一の正規データとして扱う。
- ブラウザのlocalStorageにはテーマや表示設定だけを保存する。
- 発言履歴をlocalStorageの状態復元に使わない。

開発時に別ポートでフロントエンドを起動する場合は、CORS設定が必要になる。運用時は同一オリジンへ戻す。

## 10. 専用アプリの設計

専用アプリを作る場合も、画面以外の仕様はブラウザ版と共通にする。

専用アプリが利用するもの：

- HTTPS REST API
- GET SSE
- JSONレスポンス
- Tailscale上のMagicDNS名
- 同じ状態遷移
- 同じエラーコード

専用アプリが独自に持つもの：

- ウィンドウ・画面レイアウト
- 通知
- キーボードショートカット
- 再接続表示
- サーバーURL設定

専用アプリからもOllamaへ直接接続しない。専用アプリ用の別APIを作らず、ブラウザ版と同じDebate APIを利用する。

## 11. エラー処理

### ネットワーク

- Tailscale未接続：サーバー到達不可として表示
- HTTPS証明書エラー：MagicDNS名とHTTPS設定を確認する案内
- SSE切断：再接続中表示
- サーバー再起動：状態再取得後、必要ならセッション消失を通知

### HTTP応答

- 400：入力内容を修正
- 404：セッションを再作成
- 409：現在状態を再取得
- 429：サーバー使用中。自動再送しない
- 500：サーバーエラー
- 503：Ollama利用不可またはサーバー過負荷

エラー表示は、技術的な詳細と利用者向けの説明を分ける。

## 12. セキュリティ

- Tailnet ACLで接続元を制限する。
- クライアントへOllama URLを渡さない。
- クライアントにOllama認証情報を保存しない。
- URLパラメータへテーマや発言本文を入れない。
- サーバーが返す発言本文をHTMLとして解釈せず、テキストとして表示する。
- 外部ページや画像を自動取得しない。
- 複数利用者対応が必要になった場合は、Tailnet ACLだけでなくアプリケーション認証を追加する。

## 13. ブラウザ版の受け入れ条件

- ノートPCがTailscaleへ接続した状態で画面を開ける。
- MagicDNSのHTTPS URLへアクセスできる。
- GET /healthの結果を画面に表示できる。
- テーマからセッションを作成できる。
- SSE接続後にnextを開始できる。
- tokenイベントが該当パネルへ表示される。
- turn_completed後に次の発言ボタンが有効になる。
- generating中は二重のnextを送らない。
- 429時に自動ループせず待機状態になる。
- stopが即時受付され、turn_stopped後に再操作できる。
- SSE切断時に再接続表示が出る。
- サーバー再起動後に状態消失を正しく表示できる。

## 14. 初版の対象外

- 専用アプリの実装
- 複数ノートPCからの同時操作
- 聴衆の質問送信
- クライアント間のリアルタイム同期
- オフラインでのディベート継続
- クライアント側でのLLM推論
- Ollama APIへの直接接続
