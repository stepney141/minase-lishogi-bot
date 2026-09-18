# minase-lishogi-bot

中将棋エンジン[minase](https://github.com/stepney141/minase)を、オンライン対局サイトlishogiのBotアカウントとして動かすための配備一式である。
minase本体はUSIエンジンとして呼ばれる側であり、lishogiの知識を持たない。
lishogiのBot APIとUSIの仲介は、Python製ブリッジ[nhamil/lishogi-bot](https://github.com/nhamil/lishogi-bot)を固定した版（コミットdb18bd2、2026年3月14日）でそのまま使い、改変しない。
これは[TheYoBots/Lishogi-Bot](https://github.com/TheYoBots/Lishogi-Bot)のコミット17c16bc（2024年10月26日）のフォークであり、lishogi側のAPI変更への追従（後述）を含む。

## 構成

固定した版のLishogi-Botと固定コミットのminaseを1つのDockerイメージにまとめ、運用機ではそのイメージを認証トークンだけを与えて起動する。

| ファイル | 役割 |
|---|---|
| `Dockerfile` | 2段階ビルド。第1段階はrust:1.98でminaseをビルドし、第2段階はpython:3.11-slimへLishogi-Botを固定コミットで取得して依存パッケージを入れ、minaseのバイナリと起動ラッパーを置く。コンテナは非rootユーザー（uid 10001）で動く。 |
| `compose.yml` | ビルドと起動の定義。minaseのソースは`additional_contexts`でGitHubの`minase.git`を名前付き文脈として渡し、Dockerfileが`COPY --from=minase-source`で取り込む（minase-guiと同じ方式）。ビルド時にデフォルトブランチの最新コミットを取得する。ログは名前付きボリュームに残る。 |
| `.env.example` | `.env`の雛形。認証トークンとコンテナの資源上限を置く。 |
| `minase-lishogi` | `--protocol usi --rules lishogi`を固定してminaseを起動するシェルスクリプト。 |
| `config.yml` | Lishogi-Botの設定。コンテナへ読み取り専用でマウントする。 |

`minase-lishogi`が必要なのは、Lishogi-Botの`engine_options`が使えないためである。
`engine_options`を与えるとLishogi-Botは起動コマンドを引数つきのリストのまま`shell=True`で`Popen`に渡すので、引数はシェルの位置引数になってエンジンへ届かず、`--protocol`を欠いたminaseは直ちに終了する（`engine_wrapper.py`の`create_engine`、`engine_ctrl/usi.py`の`open_process`）。

TheYoBots版ではなくnhamil版を使うのは、lishogiが2025年11月7日のコミットee46131で挑戦JSONから`speed`を削ったためである。
TheYoBots版の17c16bcは`model.py`の`Challenge.__init__`で`speed`を必須として読むので、挑戦を受け取った瞬間に`KeyError`で主ループが落ちる。
落ちた後も子プロセスがイベントストリームへ再接続し続けるためコンテナは動いたままになり、lishogi上ではBotがオンラインに見えるのに挑戦に応答しない。
nhamil版のコミットe0a3169は、`speed`が無いときに削られる前のlishogiと同じ規則で`timeControl`から求める。
推定総秒数を持ち時間＋60×加算＋25×秒読み回数×秒読み秒数とし、60秒未満をultraBullet、300秒未満をbullet、600秒未満をblitz、1,500秒未満をrapid、それ以上をclassicalとし、`perf.name`がcorrespondenceならcorrespondenceとする（scalashogiのコミット0cad44cの`Speed.byTime`と`Clock.Config.estimateTotalSeconds`と同じ境界）。
この規則により、`config.yml`の`time_controls`は従来どおりblitz、rapid、classicalの名前で指定できる。
nhamil版は17c16bcに対してこのほか、秒読みが0でないときの下限`min_nonzero_byoyomi`、挑戦者の許可リストと拒否リスト（`allow_list`、`block_list`、`bot_allow_list`、`bot_block_list`）、および京都将棋の指し手をリストで受ける修正を加えている。
いずれも設定を省略すれば無効であり、`config.yml`では使っていない。

## 前提

- Docker（Compose v2を含む）。ビルド時にGitHubからminaseとLishogi-Botを取得するので、ビルド機はネットワークに出られる必要がある。
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

4. 運用の開始と終了、使用コミット、および受け付けた対局条件を記録する。Botのプロフィールにはエンジン名、リポジトリの所在、および運用中のコミットを記す。

エンジンを更新するときは、`docker compose up --build -d`を再実行する。コンテナの再起動だけではminaseを取得し直さない。取得またはビルドに失敗した場合は更新を失敗として扱う。
更新はminaseのデフォルトブランチが進んだときに行う。
設定ファイルの変更（`Threads`、`USI_Hash`、受け付ける時間制御、`modes`への`rated`の追加）は、イメージの再ビルドを要せず、`docker compose up -d --no-build`で反映する。
`.env`のCPU数とメモリ上限は`config.yml`の`Threads`と`USI_Hash`に合わせて変え、両者を一致させる。
コンテナは非rootユーザーで動くため、`config.yml`は他ユーザーも読める644にする。

## 設定ファイル

認証トークンは`config.yml`に書かず、環境変数で上書きする。
Lishogi-Botは`token`の項目自体を必須とするので、設定ファイルには占位文字列を置いてある。
`Threads`、`USI_Hash`、受け付ける時間制御の範囲は運用パラメータであり、運用機に合わせて変える。

- `engine.name`はラッパー`minase-lishogi`を指す。`engine_options`は使わない。
- `ponder`は無効にする。minaseはponderを実装していない。
- `go_commands`は与えない。深さやノード数の上書きは時間管理を無効にする。
- `move_overhead`は1,900ミリ秒を明示する。雛形の値と、項目を省略したときのコード上の既定値（1,000ミリ秒）が異なるためである。
- 同時対局数は1にする。複数対局は探索スレッドと置換表を奪い合い、時間切れの原因になる。
- 超早指し（ultraBullet、bullet）と通信対局は受け付けない。
- 公開は非レート対局（`modes: [casual]`）から始め、異常0件を確認してから`rated`を加える。

## 時計の換算と注意

Lishogi-Botは、自分の手番で`go`を送る前に、残り時間から`move_overhead`と受信からの経過時間を引いて0で切り上げ、さらに秒読みと加算を引いて0で切り上げた値を`btime`または`wtime`に入れる。
秒読みと加算は別に`byoyomi`、`binc`、`winc`として送り、秒読みの回数（periods）は送らない。
各対局の最初の1手だけは固定の`movetime 1000`で探索する。

持ち時間が残っている間は、minaseが受け取る残り時間は実際より少なく、安全側に働く。
持ち時間が秒読み以下になると`btime`は0に切り上げられ、`move_overhead`の減算は効かない。
minaseの予算式は秒読みの8割を上限にするので、サーバへの送信遅延に使える余裕は秒読みの2割だけである。
秒読みの短い対局ほど余裕が小さいため、公開運用ではLishogi-Botのログから`go`の引数、`bestmove`の時刻、および着手送信の時刻を取り出し、lishogi側の時計と突き合わせて端到端の最小の余裕を記録する。
余裕が不足する場合は`move_overhead`を増やして対処せず、minase側の時間管理を直す。

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
