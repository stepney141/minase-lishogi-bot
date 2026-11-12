# 規則セットのオプション指定への追従の計画書

## 文書の位置付け

2026年11月12日に、中将棋エンジンminaseの側の仕様変更へ、本リポジトリの配備一式（minaseをlishogiのBotとして動かすDockerイメージ、設定、および起動用のスクリプト）を追従させる計画として起案した。
対象の変更は、minaseの計画「起動引数と診断ツールをUSIへ移す」（minaseのリポジトリの`docs/plans/archived/cli-to-usi.md`）である。
着手は、この変更を含む版のminaseがcrates.ioで公開された後、利用者の指示を待って行う。

## 目的

変更を含む版のminaseへBotを更新したときに、Botが対局を始められる状態を保つ。
配備の順序を誤るとBotが動かなくなるので、切り替える対象と確認の手順を先に定める。

## minase側の変更の要約

配備一式に影響する変更は次の2件である。

1. 起動引数`--rules`が削除される。minaseは`minase --protocol usi`で起動し、`--rules`を付けると引数の誤りとして終了コード2で終わる。
2. 規則セットの指定が必須になる。minaseは規則セット（対局に採用する規則コードの組）の既定値を持たず、USIのオプション`RuleSet`で受け取る。規則セットを設定しないまま`isready`を受けると、`info string error: required option RuleSet is not set`を出して終了コード1で終わる。

規則セット名`lishogi`は変わらない。
規則セット名`engine-default`は`JCSA`に改名されたが、配備一式はこの名前を使っていない。
Lishogi-Bot（lishogiのBot APIとUSIを仲介するブリッジ）は、エンジンの起動の後に、`usi`、`config.yml`の`usi_options`に書いた各オプションの`setoption`、`isready`の順で送るので、`usi_options`に`RuleSet`を加えれば、`isready`より前に規則セットが届く。

## 変更する箇所

次の3つを、同じコミットで切り替える。

- `Dockerfile`：`cargo install minase --version =<版>`の版を、変更を含む版へ上げる。
- `minase-lishogi`（起動用のスクリプト）：`exec /opt/minase/minase --protocol usi --rules lishogi "$@"`から`--rules lishogi`を外す。`--protocol usi`を渡すために、スクリプトは残す。Lishogi-Botが起動コマンドの引数をエンジンへ渡せない事情は変わらないからである。
- `config.yml`：`usi_options`に`RuleSet: lishogi`を加える。

あわせて、`README.md`の構成の表の`minase-lishogi`の説明（`--protocol usi --rules lishogi`を固定する）と、規則の指定に触れる記述を改める。
検査用のスクリプト`ponder_check.py`と`correspondence_check.py`は、`config.yml`を読んでLishogi-Botの関数`engine_wrapper.create_engine`でエンジンを起動するので、`config.yml`の変更がそのまま反映され、スクリプトの変更は要らない。

## 切り替えの順序を誤った場合

3つを同じコミットで切り替えるのは、一部だけを変えるとBotが動かなくなるからである。
新しいminaseを古い起動用のスクリプトで起動すると、スクリプトが渡す`--rules`が引数の誤りになり、最初の`usi`を受ける前に終了コード2で終わる。
起動用のスクリプトだけを改めて`config.yml`の`RuleSet`を加え忘れると、新しいminaseは規則セットが未設定のまま`isready`を受けて、終了コード1で終わる。
古いminaseを新しい起動用のスクリプトで起動すると、必須だった`--rules`が渡されないので起動の直後に終了する。
いずれの場合も、Lishogi-Botの側ではエンジンの異常終了として現れる。

## 検証する振る舞い

- 新しいDockerイメージの中で、Lishogi-Botがエンジンを起動する関数を実際に呼び、握手から`readyok`まで進む。起動コマンドを手で実行する確認では、ブリッジが引数を捨てる経路を通らないので、配備と同じ環境の同じ関数で確かめる。
- 握手の後、`isready`より前に`setoption name RuleSet value lishogi`がエンジンへ届いている。確認には、起動用のスクリプトに起動引数`--io-log`を一時的に足してエンジンの入出力の記録を取り、確認の後に外す。
- `ponder_check.py`、`test_correspondence.py`、`test_streams.py`、および`correspondence_check.py`が通る。
- 運用機へ配備した後、lishogiで1局を終局まで指し、時間切れとエンジンの異常終了がない。
