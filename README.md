# minase-lishogi-bot

中将棋エンジン[minase](https://github.com/stepney141/minase)を、オンライン対局サイトlishogiのBotアカウントとして動かすための配備一式である。
minase本体はUSIエンジンとして呼ばれる側であり、lishogiの知識を持たない。
lishogiのBot APIとUSIの仲介は、隣の`../lishogi-bot`に置いたPython製ブリッジ[stepney141/lishogi-bot](https://github.com/stepney141/lishogi-bot)を使う。
これは[nhamil/lishogi-bot](https://github.com/nhamil/lishogi-bot)のコミットdb18bd2（2026年3月14日）にponderと通信対局の修正を加えたフォークである。
nhamil版は[TheYoBots/Lishogi-Bot](https://github.com/TheYoBots/Lishogi-Bot)のコミット17c16bc（2024年10月26日）のフォークであり、lishogi側のAPI変更への追従（後述）を含む。

## 構成

ローカルのLishogi-BotとGitHubから取得したminaseを1つのDockerイメージにまとめ、運用機ではそのイメージを認証トークンと資源上限を与えて起動する。

| ファイル | 役割 |
|---|---|
| `Dockerfile` | 2段階ビルド。第1段階はrust:1.98でminaseをビルドし、第2段階はpython:3.11-slimへLishogi-Botのソースと依存パッケージ、minaseのバイナリ、起動ラッパーを置く。コンテナは非rootユーザー（uid 10001）で動く。 |
| `compose.yml` | ビルドと起動の定義。`additional_contexts`でGitHubの`minase.git`とローカルの`../lishogi-bot`を渡す。minaseはデフォルトブランチの最新コミットを取得し、Lishogi-Botは未コミットの変更も含めて取り込む。ログは名前付きボリュームに残る。 |
| `.env.example` | `.env`の雛形。認証トークンとコンテナの資源上限を置く。 |
| `minase-lishogi` | `--protocol usi --rules lishogi`を固定してminaseを起動するシェルスクリプト。 |
| `config.yml` | Lishogi-Botの設定。コンテナへ読み取り専用でマウントする。 |
| `ponder_check.py` | lishogiへ接続せずに、イメージの中でLishogi-Botの関数を呼んで先読み（ponder）の通信を確かめるスクリプト（後述）。 |
| `test_correspondence.py` | 挑戦の受諾、通信対局の時間管理、切断と再接続を、APIとエンジンの入出力を模擬して検証する。 |
| `correspondence_check.py` | 通信対局の対局ループで実際のminaseを60秒の予算で動かし、合法手を返すことを確かめる。 |

`minase-lishogi`が必要なのは、Lishogi-Botの`engine_options`が使えないためである。
`engine_options`を与えるとLishogi-Botは起動コマンドを引数つきのリストのまま`shell=True`で`Popen`に渡すので、引数はシェルの位置引数になってエンジンへ届かず、`--protocol`を欠いたminaseは直ちに終了する（`engine_wrapper.py`の`create_engine`、`engine_ctrl/usi.py`の`open_process`）。

TheYoBots版ではなくnhamil版を土台にするのは、lishogiが2025年11月7日のコミットee46131で挑戦JSONから`speed`を削ったためである。
TheYoBots版の17c16bcは`model.py`の`Challenge.__init__`で`speed`を必須として読むので、挑戦を受け取った瞬間に`KeyError`で主ループが落ちる。
落ちた後も子プロセスがイベントストリームへ再接続し続けるためコンテナは動いたままになり、lishogi上ではBotがオンラインに見えるのに挑戦に応答しない。
nhamil版のコミットe0a3169は、`speed`が無いときに削られる前のlishogiと同じ規則で`timeControl`から求める。
通常対局では推定総秒数を持ち時間＋60×加算＋25×秒読み回数×秒読み秒数とし、60秒未満をultraBullet、300秒未満をbullet、600秒未満をblitz、1,500秒未満をrapid、それ以上をclassicalとする（scalashogiのコミット0cad44cの`Speed.byTime`と`Clock.Config.estimateTotalSeconds`と同じ境界）。
通信対局の挑戦は`timeControl.type`で判定する。
この規則により、`config.yml`の`time_controls`は従来どおりblitz、rapid、classicalの名前で指定できる。
nhamil版は17c16bcに対してこのほか、秒読みが0でないときの下限`min_nonzero_byoyomi`、挑戦者の許可リストと拒否リスト（`allow_list`、`block_list`、`bot_allow_list`、`bot_block_list`）、および京都将棋の指し手をリストで受ける修正を加えている。
いずれも設定を省略すれば無効であり、`config.yml`では使っていない。

stepney141版は、ponderの2つの修正（コミット1cbfcb9と201af8a）と、後述する通信対局への対応を加えている。
nhamil版はStandard以外の変則で、先読みの`go ponder`に自分の着手と予想手を含まない局面を渡す。
StandardとCheckshogi以外では予想手との照合もnull手との比較になり、`ponderhit`が成立しない。
修正後は、自分の着手と予想手を加えた手順を渡し、エンジンへ送る記法の最終手と予想手を照合する。
コミット201af8aは、先読みの開始時に残り時間へ秒読みを足さないようにする。
lishogiの時計は、持ち時間が尽きた後は1手ごとに残り時間を秒読みの長さへ戻すので、サーバが知らせる残り時間には秒読みが含まれている。
修正前は、足した秒読みを`go`の送信部が引き直して打ち消し合い、秒読みの消化中の`go ponder`が、実際には残っていない持ち時間を`btime`または`wtime`として送っていた。
修正後は通常の`go`と同じ規約になり、秒読みの消化中は残り時間0と秒読みを送る。

## 前提

- Docker（Compose v2を含む）が必要である。ビルド時にGitHubからminaseを取得するので、ビルド機はネットワークに出られる必要がある。
- 通信対局の修正を含むLishogi-Botのソースを`../lishogi-bot`に置く。DockerfileはPythonのソースと`engine_ctrl`、依存パッケージの一覧だけを取り込み、そのリポジトリの設定ファイルは取り込まない。
- `bot:play`スコープの認証トークン。対局履歴のない新規アカウントで発行する。昇格は取り消せず、一度でも対局したアカウントは昇格できない。

## 手順

1. `.env.example`を`.env`へ複製し、トークンを`LISHOGI_BOT_TOKEN`に書く。`.env`はGit管理の対象外である。

2. 初回だけ、Botを起動せずにアカウントを昇格する。Lishogi-Botの`-u`は昇格後にそのまま挑戦の待受へ進むので使わず、同じAPIを直接呼ぶ。応答が`{"ok":true}`であることを確かめる。

   ```console
   curl -X POST https://lishogi.org/api/bot/account/upgrade -H "Authorization: Bearer $LISHOGI_BOT_TOKEN"
   ```

3. minaseのデフォルトブランチの最新コミットを取得・ビルドして起動し、挑戦の待受に入ったことと認証エラーがないことをログで確かめる。同じアカウントのBotを2つ起動しない。ビルド時点のコミットは`git ls-remote https://github.com/stepney141/minase.git HEAD`で確かめて記録する。

   ```console
   docker compose up --build -d
   docker compose logs -f
   ```

4. 運用の開始と終了、使用コミット、および受け付けた対局条件を記録する。Lishogi-Botは`git -C ../lishogi-bot rev-parse HEAD`と`git -C ../lishogi-bot diff`でビルドしたソースを記録する。Botのプロフィールにはエンジン名、リポジトリの所在、および運用中のコミットを記す。

エンジンを更新するときは、`docker compose up --build -d`を再実行する。コンテナの再起動だけではminaseを取得し直さない。取得またはビルドに失敗した場合は更新を失敗として扱う。
更新はminaseのデフォルトブランチが進んだときに行う。
Lishogi-Botのコードを変更した場合も再ビルドする。
設定ファイルだけの変更は、イメージの再ビルドを要せず、`docker compose up -d --no-build --force-recreate`で反映する。
`.env`のCPU数は`config.yml`の`Threads`に同時対局数を掛けた値にし、メモリ上限は`USI_Hash`に同時対局数を掛けた値より大きくする。
コンテナは非rootユーザーで動くため、`config.yml`は他ユーザーも読める644にする。

## 設定ファイル

認証トークンは`config.yml`に書かず、環境変数で上書きする。
Lishogi-Botは`token`の項目自体を必須とするので、設定ファイルには占位文字列を置いてある。
`Threads`、`USI_Hash`、受け付ける時間制御の範囲は運用パラメータであり、運用機に合わせて変える。

- `engine.name`はラッパー`minase-lishogi`を指す。`engine_options`は使わない。
- 通常対局では`engine.ponder`を有効にし、通信対局では`correspondence.ponder`を無効にする。minaseは`bestmove`に予想手を付け、`go ponder`と`ponderhit`に対応する（minaseの`docs/plans/ponder.md`）。先読みの間も`Threads`の数だけCPUを使うので、コンテナのCPU数は「`Threads`×同時対局数」を下回らないようにする。
- `go_commands`は与えない。深さやノード数の上書きは時間管理を無効にする。
- `move_overhead`は1,900ミリ秒を明示する。雛形の値と、項目を省略したときのコード上の既定値（1,000ミリ秒）が異なるためである。
- 同時対局数（`challenge.concurrency`）は2にする。Lishogi-Botは対局ごとにエンジンのプロセスを1つ起動するので、`Threads`と`USI_Hash`は1局あたりの値である。コンテナのCPU数とメモリ上限を2局分にしておけば、対局どうしが探索スレッドと置換表を奪い合うことはない。
- 超早指し（ultraBullet、bullet）は受け付けず、blitz、rapid、classicalと通信対局を受け付ける。
- 公開は非レート対局（`modes: [casual]`）から始め、異常0件を確認してから`rated`を加える。

## 通信対局

通信対局では初手から1手60秒を思考時間の上限とし、相手の手番では先読みしない。
残り時間が少ないときは、残り時間から通信の余裕と処理の経過時間を引いた値まで思考時間を短縮する。
その値が0以下なら、エンジンには最小の1ミリ秒を指定する。
対局上の期限は挑戦者が指定する1手あたり1、2、3、5、7、10、14日であり、ボットの思考時間とは別である。
`max_base`と`min_base`は通常対局の受諾条件であり、通信対局の日数を制限しない。

着手後は相手の応手を150秒待ち、応手がなければ接続を閉じてエンジンを終了する。
ボットは600秒ごとに、処理枠に空きがあれば待機中の対局へ再接続する。
序盤の30秒自動中断は通常対局だけに適用するため、通信対局では相手がすぐに指さなくても中断しない。
再起動時もイベントストリームに届く進行中の対局を開き、対局ストリームの時計の有無で通常対局と通信対局を判定する。

この判定には`perf`を使わない。
中将棋では通信対局でも`perf`が中将棋を示すため、挑戦の`timeControl.type`と対局ストリームの`clock`を使う（[挑戦の出力形式](https://github.com/WandererXII/lishogi/blob/master/modules/challenge/src/main/JsonView.scala)、[対局ストリームの出力形式](https://github.com/WandererXII/lishogi/blob/master/modules/bot/src/main/BotJsonView.scala)）。

修正後のイメージをビルドし、次の2つの検証を行う。
前者は受諾条件、思考時間、序盤の待機、切断後と再起動後の再開、終局時の解放を検証する。
後者は実際のminaseを起動し、初手に`go movetime 60000`を送り、合法手が返ることを確認する。
いずれも認証トークンを渡さず、ネットワークを無効にして実行する。

```console
docker compose build
docker run --rm --network none \
  -v ./config.yml:/opt/lishogi-bot/config.yml:ro \
  -v ./test_correspondence.py:/opt/lishogi-bot/test_correspondence.py:ro \
  --entrypoint python3 minase-lishogi-bot-bot \
  -m pytest -q -p no:cacheprovider test_correspondence.py
docker run --rm --network none --cpus 4 \
  -v ./config.yml:/opt/lishogi-bot/config.yml:ro \
  -v ./correspondence_check.py:/opt/lishogi-bot/correspondence_check.py:ro \
  --entrypoint python3 minase-lishogi-bot-bot correspondence_check.py
```

## 通常対局の時計の換算と注意

Lishogi-Botは、自分の手番で`go`を送る前に、残り時間から`move_overhead`と受信からの経過時間を引いて0で切り上げ、さらに秒読みと加算を引いて0で切り上げた値を`btime`または`wtime`に入れる。
秒読みと加算は別に`byoyomi`、`binc`、`winc`として送り、秒読みの回数（periods）は送らない。
各対局の最初の1手だけは固定の`movetime 1000`で探索する。

持ち時間が残っている間は、minaseが受け取る残り時間は実際より少なく、安全側に働く。
持ち時間が秒読み以下になると`btime`は0に切り上げられ、`move_overhead`の減算は効かない。
minaseの予算式は秒読みの8割を上限にするので、サーバへの送信遅延に使える余裕は秒読みの2割だけである。
秒読みの短い対局ほど余裕が小さいため、公開運用ではLishogi-Botのログから`go`の引数、`bestmove`の時刻、および着手送信の時刻を取り出し、lishogi側の時計と突き合わせて端到端の最小の余裕を記録する。
余裕が不足する場合は`move_overhead`を増やして対処せず、minase側の時間管理を直す。

## 先読みの通信の確認

`ponder_check.py`は、lishogiへ接続せずに、配備と同じイメージの中でLishogi-Botの関数（`play_midgame_move`、`start_pondering`、`get_pondering_result`、および終局時の停止）を対局ループと同じ順に呼び、エンジンとの送受信を確かめる。
確かめる内容は、`go ponder`の局面が自分の着手と予想手を含むこと、`ponderhit`または`stop`より前に`bestmove`が届かないこと、的中で`ponderhit`だけが送られること、外れで`stop`の後に`bestmove`が1回だけ届いて通常の`go`へ進めること、秒読みの消化中の`go ponder`が残り時間0と秒読みを送り、的中後の思考が秒読みに収まること、および先読み中の終局で`position`、`stop`、`quit`の後にエンジンが終了することである。
Lishogi-Botのコード、minase、または`config.yml`の`ponder`を変えたときに、イメージをビルドしてから次のコマンドで実行し、最後に`ALL CHECKS PASSED`が出ることを確かめる。
スクリプトの実行には認証トークンを使わず、運用中のコンテナにも触れない。

```console
docker compose build
docker run --rm --cpus 8 \
  -v ./config.yml:/opt/lishogi-bot/config.yml:ro \
  -v ./ponder_check.py:/opt/lishogi-bot/ponder_check.py:ro \
  --entrypoint python3 minase-lishogi-bot-bot ponder_check.py
```

## 事後照合

受諾した全対局を母数として、完走した対局をlishogi APIから取得し、minaseの`--rules lishogi`で再生して各手の受理と終局裁定の一致を確かめる。
取得は`/api/games/user/<Bot名>?perfType=chushogi&moves=true`で行う。
Lishogi-Botのログからは、`position`の拒否、`bestmove`の欠落、エンジンプロセスの異常終了と残存、および時間切れ負けの件数を数え、いずれも0件であることを要する。
完走しなかった対局は、無活動による中断、相手の切断、Lishogi-Botの通信例外、および対局ストリームの終了に理由を分け、minase側に起因するものが0件であることを確かめる。

## 未確認事項

lishogiがBotへの挑戦で途中局面からの開始を許すかどうかは未確認である。
Lishogi-Botは途中局面の`initialSfen`をそのままminaseへ渡す一方、自分の手番判定には着手数だけを使うため、後手番から始まる局面では両者の手番判定が食い違う。
許される場合は先手番開始と後手番開始の両方を試し、後手番開始で正しく動かなければ、その開始形の挑戦を受け付けない運用を定める。

## 参考

- minaseの設計書 `docs/plans/lishogi-bot.md`（反復規則R1のlishogiとの整合、および完了条件）。
- minaseの `docs/protocols/usi-lishogi.md`（USIのlishogi系拡張とLishogi-Botの対局進行の調査記録）。
