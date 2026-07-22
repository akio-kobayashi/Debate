# Debate Demo

学生に見せるための、教員操作型ブラウザ画面です。A・B・Cの3パネル、上部のテーマと9ターン進捗、下部の進行履歴を1画面に収めています。

## 起動方法

Debate APIが画面も配信するため、通常はAPIのURLをブラウザで開きます。

~~~text
http://<overlay-ip>:8000/
~~~

APIと別に静的配信する場合は、次のようにできます。

~~~bash
cd Debate
python3 -m http.server 4173 --directory demo
~~~

## デモの範囲

- テーマ入力
- Cによるテーマ整理
- 教員が押す「次の発言」
- A・B・Cの逐次生成とSSE表示
- 停止、リセット、再接続
- 9ターンの進行履歴表示

Google Formの回答取得・分析とGoogle Drive保存は、[GOOGLE_WORKSPACE_SETUP.md](../GOOGLE_WORKSPACE_SETUP.md)を参照してください。
