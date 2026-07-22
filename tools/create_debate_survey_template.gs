/**
 * Debate Demoの質問テンプレートをGoogle Formとして作成する。
 *
 * 実行方法：
 * 1. script.google.com で新しいプロジェクトを作成する。
 * 2. このファイルの内容を貼り付ける。
 * 3. createDebateSurveyTemplate を実行して権限を承認する。
 * 4. 実行ログに表示された編集URLのフォームを、対象フォームから質問インポートに使う。
 */
function createDebateSurveyTemplate() {
  var form = FormApp.create('Debate Demo 振り返りアンケート');
  form.setDescription(
    'ディベートの最終整理を確認したうえで回答してください。' +
    '主張・根拠・反論・ファシリテーターの整理を評価することが目的です。'
  );
  form.setConfirmationMessage('回答ありがとうございました。');

  addMultipleChoice(form, '今回のテーマについて、現在のあなたの考えに最も近いものを選んでください。', [
    '強く賛成',
    'やや賛成',
    'どちらともいえない',
    'やや反対',
    '強く反対',
  ]);

  form.addSectionHeaderItem().setTitle('主張と根拠の評価');

  addMultipleChoice(form, 'AとBのどちらの立場の方が、全体として説得力があると感じましたか。', [
    'A（賛成側）',
    'B（反対側）',
    'AとBは同程度',
    'どちらとも判断できない',
  ]);

  addMultipleChoice(form, '最も説得力があると考えた主張を1つ選んでください。', [
    'Aの第1論点',
    'Aの第2論点',
    'Aの第3論点',
    'Bの第1論点',
    'Bの第2論点',
    'Bの第3論点',
    '判断できない',
  ]);

  addMultipleChoice(form, '選んだ主張を説得的だと考えた主な理由を1つ選んでください。', [
    '主張と根拠の関係が明確だった',
    '具体例・データ・事実が示されていた',
    '相手の反論に適切に答えていた',
    '実現可能性が高かった',
    '用語や前提が明確だった',
    '表現が分かりやすかった',
    '特に理由はない',
  ]);

  addMultipleChoice(form, '追加の確認・検証が最も必要だと思う主張を1つ選んでください。', [
    'Aの第1論点',
    'Aの第2論点',
    'Aの第3論点',
    'Bの第1論点',
    'Bの第2論点',
    'Bの第3論点',
    'AとBの両方',
    '特にない',
  ]);

  form.addSectionHeaderItem().setTitle('反論とファシリテーターの評価');

  addMultipleChoice(form, '自分の最初の考えを見直すきっかけになったものを1つ選んでください。', [
    'Aの主張',
    'Bの主張',
    'AからBへの反論',
    'BからAへの反論',
    'Cの論点整理',
    'Cの最終まとめ',
    '特にない',
  ]);

  addMultipleChoice(form, 'Cの最終整理について、最も近い評価を1つ選んでください。', [
    'AとBの主張を公平に整理していた',
    'A側の主張を十分に扱っていなかった',
    'B側の主張を十分に扱っていなかった',
    '対立点と合意点を適切に区別していた',
    '未解決の論点を適切に示していた',
    '根拠のない結論を追加していた',
    '判断できない',
  ]);

  form.addSectionHeaderItem().setTitle('LLMへの指示と転移');

  addMultipleChoice(form, '次回、LLMに最初に追加すべき指示を1つ選んでください。', [
    '主張ごとに根拠や出典を示すよう求める',
    '相手の最も強い反論に答えるよう求める',
    '用語や前提を明確にするよう求める',
    '不確実な点を明示するよう求める',
    '具体例を追加するよう求める',
    '反論と再反論を対応付けるよう求める',
    '発言を短く整理するよう求める',
  ]);

  addMultipleChoice(form, '今回のテーマと類似した新しい状況では、どの判断をしますか。', [
    '類似した状況でも賛成する',
    '類似した状況でも反対する',
    '条件によって判断が変わる',
    '追加情報を確認してから判断する',
    '判断できない',
  ]);

  form.addScaleItem()
    .setTitle('今回の自分の回答にどの程度自信がありますか。')
    .setBounds(1, 5)
    .setLabels('まったく自信がない', '非常に自信がある')
    .setRequired(true);

  Logger.log('編集URL: ' + form.getEditUrl());
}

function addMultipleChoice(form, title, choices) {
  form.addMultipleChoiceItem()
    .setTitle(title)
    .setChoiceValues(choices)
    .setRequired(true);
}
