# 常時稼働させる運用機の比較

2026年10月24日と25日に、Botを常時稼働させる運用機の候補を、専有サーバー、共有vCPUのVPS、専有vCPUのクラウドの3種類について調べた。
前提は、同時に3局を受け付けることと、運用者が日本に住んでいることである。
現在のBotは、日本にある運用者の手元の機械でDockerのコンテナとして動いている。
AWSのEC2の試算は[AWS運用費用の比較](aws-pricing.md)にあるので、本書では繰り返さない。
本書は料金、提供地域、および利用規約の調査であり、候補機での探索速度は測っていない。
Hetzner、OVHcloud、およびnetcupは2026年に値上げをしたので、料金は取得した日の値として扱う。

## 3局に必要な資源

[config.yml](../../config.yml)は1局あたり`Threads: 4`と`USI_Hash: 2048`を指定し、相手の手番中も先読みする。
`USI_Hash`は置換表の大きさで、単位はMBである。
3局がすべて探索している間は12スレッドが全力で動き、置換表だけで6 GiBを使う。
1局あたりの資源を現行の同時2局の運用と同じに保つには、物理12コアとメモリ16 GB以上が目安になる。
1局を2スレッドに減らせば物理6コアでも3局を指せるが、1局あたりの探索量は減る。

変える設定は3か所ある。
`challenge.concurrency`を3にし、[.env.example](../../.env.example)の規則に従ってCPU上限を`Threads`の3倍の12にする。
メモリ上限は置換表の合計6 GiBより大きくする。
現行の2局では置換表4 GiBに対して上限を6 GBとしているので、同じ比率なら9 GB程度になる。

ディスクには、運用機でminaseをビルドするための`rust:1.98-bookworm`イメージ（2.2 GB）と、実行用のイメージ（約260 MB）を置く。
ビルド中のキャッシュの大きさは測っていない。
Botのログは2026年9月18日から10月24日までの36日間で671 MBに増えたので、ログの容量の管理も必要になる。

## Botの実際の負荷

先読みがあるので、Botは常に全力でCPUを使うようにも見える。
実際の負荷を知るため、Botのログ`logs/lishogi-bot.log`から、エンジンが探索していた時間を集計した。
対象は2026年9月18日04:28から10月24日14:33（UTC）までの36.4日間で、この間の同時対局数は2である。

集計では、エンジンへの`go`（USIの探索開始の命令）の送信で探索が1つ始まり、エンジンからの`bestmove`（着手の応答）の受信で1つ終わるとみなして、同時に探索している数を時刻ごとに数えた。
先読みの`go ponder`も、予想が外れて止めた探索も、最後には`bestmove`を返すので、この方法で探索中の数を数えられる。
Botを起動した37回は、その時点で同時に探索している数を0に戻した。
`bestmove`の記録漏れがあると数が0に戻らない。
通信対局の1手の上限300秒の2倍にあたる600秒を超えて、探索中のまま送受信がなかった時間は合計3.7時間であり、記録漏れの影響はこの程度にとどまる。

| 同時に探索していた数 | 時間 | 割合 |
|---|---:|---:|
| 0 | 424.6時間 | 48.6% |
| 1 | 321.0時間 | 36.7% |
| 2 | 117.8時間 | 13.5% |
| 3以上 | 10.7時間 | 1.2% |

同時対局数が2なので、3以上の行は記録漏れによる数え過ぎと考えられる。
同時に探索していた数の平均は0.68で、1局4スレッドで換算すると平均約2.7スレッドになる。
稼働を始めた直後の数日を除くと、1局以上が探索していた時間は、最も少ない10月2日で1日の24%、最も多い10月16日で88%だった。
負荷は断続的だが、対局の多い日には全スレッドを使う探索が何時間も続く。
同時対局数を3にすれば、これまで断っていた挑戦も受けるので、同時に探索している数の平均は上がる。

## 共有vCPUの懸念

共有vCPUのVPSでは、複数の利用者の仮想CPUが同じ物理CPUを分け合う。
他の利用者のCPU負荷が高いと、自分の仮想CPUは物理CPUの空きを待たされ、この待ち時間をstealと呼ぶ。
minaseは持ち時間を実時間で管理するので、待たされた分だけ読める量が減り、その対局でのminaseの強さが落ちる。
仮想CPUの停止が数秒に及べば、秒読みで着手を送る余裕も削られる。

vpsbenchmarks.comは各社の共有プランで持続負荷の試験を公開しているが、各コアの負荷を50%に抑えた試験である。
その試験でのstealの最大は、Hetzner CX23が0.00%（2026年8月28日）、Contabo Cloud VPS 18が0.00%（2026年9月8日）、OVHcloudの米国のVPS-4 2027が0.02%（2026年9月18日）、Vultr Regularが0.45%（2026年4月30日）、DigitalOcean Basicが1.50%（2025年9月16日）だった。
12スレッドを何時間も全力で動かしたときのstealを測った資料は見つからなかった。
netcupは自社のブログ（2026年5月13日）で「Only sustained full load across multiple cores will make it visible that you do share hardware.」と書いており、Botの対局の多い日はこの状況に当たる。

vCPUの数は物理コアの数と一致しない。
DigitalOceanは共有プランのvCPUを1つのハイパースレッドと説明し、VultrのAPIはvCPUの種類を`thread`と返す。
1 vCPUがSMT（同時マルチスレッディング）の1スレッドであれば、12 vCPUの処理量は物理6コア程度にとどまることがある。
これは専有vCPUのプランにも当てはまる。

### 高負荷に関する各社の規約

規約の扱いは事業者ごとに違う。

| 事業者 | 規約の記述 | 本用途への影響 |
|---|---|---|
| netcup | 一般取引条件の第5条が、CPUに特に高い負荷をかけるサーバーサービスを禁じたうえで、「this does not apply in the case of dedicated server and virtual servers」と除外する | 明文上は問題ない |
| OVHcloud | CPUの使用に関する公式の記述は見つからなかった | 不明 |
| Contabo | 一般取引条件の第9条第1項が「Any scripts and programs that could potentially extensively wear and/or tear Provider's hardware or bandwidth」を禁じる | 解釈による |
| Hetzner | 共有プランを「designed for variable usage patterns rather than sustained high workloads」と説明する | 想定外の使い方になる |
| Linode | 共有CPUは「should remain below 80% sustained usage on average」と求める | 対局の多い日には超える |
| Vultr | 利用規約で、CPUを過剰に使うインスタンスのCPUを制限する権利を留保する | 制限されうる |
| DigitalOcean | 利用規約で、システムの資源を不均衡に消費する使い方を禁じる | 解釈による |
| さくらのVPS | 約款が「各計算資源を恒常的に占有することはできません」と定め、制限の閾値は過去のデータの平均値で測ると説明する | 本用途には使えない |
| ConoHa、XServer、シンVPS、ABLENET | 設備に著しい負荷をかける行為や、他の利用者に支障を与える行為を禁じる一般条項だけがある | 解釈による |

## 専有サーバーと専有コアのVPS

この節の候補のうち、物理コアを確実に専有できるのは専有サーバーである。

| プラン | CPU | 物理コア／スレッド | メモリ | 所在地 | 月額 | 初期費用 |
|---|---|---|---|---|---|---|
| OVHcloud RISE-3 | Ryzen 9 5900X | 12／24 | 64 GB | 米国Hillsboro | 147ドル、税抜き | 110ドル、12か月前払いなら0 |
| Hetzner AX102 | Ryzen 9 7950X3D | 16／32 | 128 GB | ドイツ、フィンランド | 159ユーロ、税抜き | 129ユーロ |
| netcup RS 4000 G12.5 | EPYC 9645 | 専有12コア、内訳は非公表 | 32 GB | 米国Manassas、欧州ほか | 77.83ユーロ、税抜き、12か月契約 | 記載なし |
| Contabo Cloud VDS L | EPYC 7282 | 仮想12コア、内訳は非公表 | 48 GB | 米国、欧州ほか | 69.60ユーロ、税込み、24か月契約時の月額 | 0 |
| OVHcloud RISE-1 | Xeon E-2386G | 6／12 | 32 GB | 米国Hillsboro | 70ドル、税抜き | 70ドル、12か月前払いなら0 |
| Hetzner AX42 | Ryzen 7 PRO 8700GE | 8／16 | 64 GB | ドイツ、フィンランド | 79ユーロ、税抜き | 49ユーロ |
| Hetzner EX44 | Core i5-13500 | 高性能6＋高効率8／20 | 64 GB | ドイツ、フィンランド | 59ユーロ、税抜き | 0 |
| Hetzner AX41 | Ryzen 5 3600 | 6／12 | 64 GB | ドイツ、フィンランド | 59ユーロ、税抜き | 0 |
| netcup RS 2000 G12.5 | EPYC 9645 | 専有8コア、内訳は非公表 | 16 GB | 米国Manassas、欧州ほか | 40.70ユーロ、税抜き、12か月契約 | 記載なし |

RISE-3の定価は、メモリ32 GBとNVMe 512 GB×2の基本構成で月110ドルである。
2026年10月24日にOVHcloudの公開APIで在庫を調べると、Hillsboroにはメモリかディスクを増やした構成しかなかった。
在庫のある最安の構成はメモリ64 GBとNVMe 960 GB×2で、月額は110ドルに13ドルと24ドルを加えた147ドルになる。
APIの応答では在庫が「少量」であり、注文までに売り切れることがある。
物理8コアのRyzen 7 9700Xを積むRISE-S（月77ドル）は、カナダと欧州だけで提供され、米国にはない。

米国の拠点であるHillsboroとVint HillのサーバーはOVHcloudの米国法人だけが販売し、公式FAQは、他の法人のアカウントから米国のサーバーは注文できず、米国法人で別のアカウントを作る必要があると説明する。
日本に住む個人が米国法人のアカウントを作れるかは、公式の説明が見つからなかった。

netcupとContaboは、「コア」が物理コアかSMTのスレッドかを公式に明記していない。
ContaboのVDS XXLは、物理16コアのEPYC 7282で24コアを提供しているので、少なくともその一部はスレッドを1コアと数えている。

Hetznerのサーバーオークションは、2026年10月24日の時点で新品より高かった。
Ryzen 5 3600の機種は月71ユーロからで、同じCPUの新品AX41の59ユーロを上回る。
オークションの価格は時間とともに下がる仕組みなので、この差は変わることがある。

## 共有vCPUのVPS

月額は、契約期間の縛りがない場合の値である。

| プラン | vCPU／メモリ／ディスク | 所在地 | 月額 | 長期契約の月額 |
|---|---|---|---|---|
| OVHcloud VPS-4 2026 | 12／48 GB／300 GB | 米国オレゴン、米国東部 | 43.50ドル、税抜き | 12か月前払いで36.98ドル |
| OVHcloud VPS-3 2026 | 8／24 GB／200 GB | 同上 | 23.50ドル、税抜き | 12か月前払いで19.97ドル |
| OVHcloud VPS-4 2027 | 8／24 GB／200 GB | 同上 | 27.50ドル、税抜き | 12か月前払いで23.37ドル |
| OVHcloud VPS-3 2027 | 6／12 GB／100 GB | 同上 | 14.50ドル、税抜き | 12か月前払いで12.32ドル |
| Contabo Cloud VPS 12 | 12／48 GB／400 GB | 米国Seattleほか | 25.00ユーロに所在地加算、Seattleは7.15ユーロ | 12か月で15%引き、24か月で20%引き |
| Contabo Cloud VPS 8 | 8／24 GB／300 GB | 同上 | 14.00ユーロに所在地加算、Seattleは4.00ユーロ | 同上 |
| netcup VPS 4000 G12.5 | 12／32 GB／512 GB | 米国Manassas、欧州ほか | 43.83ユーロ、税抜き | 24か月で32.40ユーロ |
| netcup VPS 2000 G12.5 | 8／16 GB／256 GB | 同上 | 26.02ユーロ、税抜き | 24か月で19.24ユーロ |
| Hetzner CPX52 | 12／24 GB／480 GB | 欧州、シンガポール | 100.99ユーロ、税抜き | なし |
| Hetzner CPX42 | 8／16 GB／320 GB | 欧州 | 69.99ユーロ、税抜き | なし |
| Hetzner CPX41 | 8／16 GB／240 GB | 米国Ashburn、Hillsboro | 142.09ドル、税抜き | なし |
| Vultr High Performance | 12／24 GB／500 GB | 米国西部ほか | 144ドル | なし |
| Linode Shared 16GB | 6／16 GB／320 GB | 米国西部ほか | 96ドル | なし |
| ABLENET VPS L7 | 12／64 GB／800 GB | 大阪 | 29,440円、税込み | 年払いで23,328円 |
| ABLENET VPS L5 | 8／16 GB／300 GB | 大阪 | 5,872円、税込み | 年払いで4,560円 |
| XServer VPS 32GB | 12／32 GB／1,600 GB | 国内 | 26,510円、税込み | 36か月で22,220円 |
| XServer VPS 16GB | 8／16 GB／800 GB | 国内 | 11,770円、税込み | 36か月で8,690円 |
| ConoHa VPS 48GB | 12／48 GB／100 GB | 国内 | 19,448円、税込み | 36か月で13,313円 |

OVHcloudでは、2026年版のVPS-3が同じ性能の2027年版VPS-4より安い。
2026年版の2プランは公式のカタログAPIでオレゴンでの提供を確認したが、米国のWebサイトには2027年版だけが載っており、サイトから注文できるかは確かめていない。
オレゴンのVPSも、RISE-3と同じくOVHcloudの米国法人が販売する。

Hetznerは、2026年6月15日の価格改定で共有プランも値上がりした。
安価な共有プランであるx86のCXとArmのCAXは欧州だけで提供され、10月24日のWebサイトでは「not available」と表示されていた。
Vultr、DigitalOcean、およびLinodeの共有プランは、8〜12 vCPUで月80〜192ドルになる。

国内では、ConoHaの1か月の価格は10月29日までのキャンペーン価格で、更新時は22,099円になる。
国内の候補として調べたKAGOYA CLOUD VPSは、Linuxカーネルの脆弱性への対応のため、10月19日から新規申込を止めている。
さくらのVPSは、前節の約款により本用途には使えない。
国内のVPSは、日本にある今の運用機と同じく、日本からlishogiへ接続する。

## 専有vCPUのクラウドとクレジット型

| プラン | 中身 | 所在地 | 月額 |
|---|---|---|---|
| Oracle Cloud A1.Flex、12 OCPU（1 OCPUは物理1コア）、16 GB | Armの物理12コア | 米国San Jose、Phoenix | 57.60ドルまたは76.62ドル |
| Oracle Cloud E6.Flex、6 OCPU、16 GB | x86の物理6コア、12スレッド | 同上 | 154.76ドル |
| Hetzner CCX33 | 専有8 vCPU | 米国Ashburn、Hillsboro | 140.99ユーロ、税抜き |
| Linode G6 Dedicated 16GB | 8 vCPU、16 GB | 米国西部 | 144ドル |
| Vultr Optimized CPU | 8 vCPU、16 GB | 米国西部 | 160ドル |
| DigitalOcean CPU-Optimized | 8 vCPU、16 GB | 米国西部 | 168ドル |
| Lightsail Compute-optimized | 8 vCPU、16 GB | 米国オレゴン | 168ドル |
| Azure D8als_v7 | 8 vCPU、16 GB | 米国西部 | 235.06ドル |
| Google Cloud t2d-standard-8 | 8 vCPU、32 GB | 米国西部 | 246.72ドル |
| さくらのクラウド コア専有 | 8コア、16 GB | 東京、石狩 | 42,020円、税込み |

Oracle Cloudの月額は、時間単価に730時間を掛けて求めた。
E6.Flexは1 OCPUあたり毎時0.03ドル、メモリは1 GBあたり毎時0.002ドルである。
x86の専有vCPUは、どれも物理12コアのRISE-3より高い。

Oracle CloudのA1は、1 OCPUが物理1コアなので、物理12コアを月60〜80ドル程度で使える。
月額が2通りあるのは、無料分についてOracleの料金表と無料枠の説明ページが食い違うためである。
料金表では毎月3,000 OCPU時間と18,000 GB時間が無料で、残りを1 OCPUあたり毎時0.01ドルで計算すると57.60ドルになる。
無料枠のページでは無料分が1,500 OCPU時間と9,000 GB時間で、同じ計算で76.62ドルになる。
ただしA1はArmであり、minaseはArmでのビルドも性能の測定もしていない。
[AWS運用費用の比較](aws-pricing.md)は、x86より性能が下がるArmの構成は安くても採らないとしているので、A1はArmで性能を確かめた場合に限る候補である。

AWSのT系、Azure B系、およびLightsailの汎用プランは、平均の使用率が基準を超えると減速するか追加料金がかかるクレジット型である。
T系は最大8 vCPUで、基準性能は1 vCPUあたり40%なので、合わせて3.2 vCPU分になる。
対局の多い日の負荷は、1局以上が探索していた割合88%に4スレッドを掛けた3.52スレッド以上なので、この基準を超える。
8〜16 vCPUのインスタンスで計算すると、全力の探索が続けば、貯めたクレジットは10〜16時間で尽きる。
その後、Azure B系とLightsailは対局中でも基準性能まで減速する。
AWSのUnlimitedモードは速度を保つが、8スレッドが全力で続くと、1 vCPU時間あたり0.05ドルの追加料金が月に最大約175ドルかかる。
クレジット型は本用途に向かない。

## 候補の絞り方

1局あたりの資源を今と同じに保つなら、物理12コアを専有できる機種が要る。
最も安いのはOVHcloudのRISE-3で、lishogiのサーバーがある米国西部に置ける点でも有利である[^lishogi]。
米国法人のアカウントを作れない場合は、欧州に置くことになるがHetzner AX102が確実な候補になる。
Oracle CloudのA1は、Armで性能を確かめられれば、この2つより安い。

共有vCPUで安く済ませるなら、米国西部ではOVHcloudのオレゴンの12 vCPUが月43.50ドルで最も安い。
米国法人と契約できない場合は、ContaboのSeattleの12 vCPUが代わりになるが、ハードウェアの消耗を禁じる条項の解釈が残る。
規約上の扱いが最も明確なのはnetcupのVPS 4000で、所在は米国東部か欧州になる。

国内に置くなら、ABLENETが最も安い。
L5（8 vCPU、16 GB）の月5,872円は、今回見つかった8 vCPUのプランの中で国内外を通じて最も安かったが、3局では1局を2スレッドに減らすことになる。
1局4スレッドを保つにはL7（12 vCPU、64 GB）が要る。

共有vCPUのどの候補も、全力時のstealは測られていない。
契約前の判断材料が足りないので、月単位で解約でき初期費用のないプランで1か月試してから決める。
OVHcloudの縛りなしのVPS、Contabo、netcupの1か月契約、ABLENETの月払いがこれに当たる。
試用中には次の3点を確かめる。

1. 12スレッドを数時間全力で動かし、`/proc/stat`か`top`でstealの割合を見る。
2. minaseの探索速度を測る`bench`を動かし、今の運用機と比べる。
3. 実際の対局で、秒読み中の時間切れが出ないことを確かめる。

[^lishogi]: lishogiは2026年3月4日の[公式告知](https://lishogi.org/blog/post/aZ10yRIAACsA2sRy)で、メインサーバーを欧州から米国西部へ移したと説明している。

## 移す前に決めること

[Dockerfile](../../Dockerfile)は`-C target-cpu=native`でminaseをビルドし、ビルドしたホストのCPUが持つ命令拡張を使う。
専有サーバーではCPUが変わらないので問題にならない。
仮想マシンでは、別のホストへ移されて使える命令拡張が変わると、エンジンが不正命令で止まるおそれがある。
仮想マシンを選ぶ場合は、`x86-64-v3`のような固定の水準でビルドするかを決める必要がある。

config.ymlの`ByoyomiMargin: 3000`は、秒読みの締切前に残す余裕であり、単位はミリ秒である。
この値は、今の運用機からlishogiへ着手を送るときの往復時間の実測をもとに決めた。
国内に置けば同じ条件が続くが、米国や欧州に置く場合は移転後に往復時間を測り直す。
[README](../../README.md)は、余裕が足りない場合に`move_overhead`ではなく`ByoyomiMargin`を上げるとしている。

同じBotアカウントを2台で同時に動かさないよう、新しい運用機で起動する前に、今の運用機で動いているBotのコンテナを止める。

## 未確認の条件

次の値は、事業者の公式ページを1回読み取っただけで、再確認していない。

- ContaboのSeattleの所在地加算額と、Contaboの価格の税区分は、発注画面を1回読んだだけである。
- netcupのVPSの税抜き価格は、税込みの表示額から計算した値である。
- netcupのManassasの所在地加算額は、24か月契約の構成画面でしか確かめていない。
- Oracle CloudのE6.FlexがSan JoseとPhoenixで提供されていることは、日付のない第三者のサイトにしか記載がない。
- LightsailのCompute-optimizedがオレゴンで提供されていることは確かめていない。

このほか、OVHcloudの米国法人と日本在住の個人の契約の可否、OVHcloudの2026年版VPSのWebサイトからの注文の可否、netcupとContaboのコアの内訳、および各候補の全力時のstealと探索速度は確かめていない。
本書の作成にあたって、どの事業者のアカウントも作っておらず、資源も借りていない。

## 出典

価格は2026年10月24日と25日に、各社の公式ページ、公開API、または発注画面から取得した。
規約は同じ期間に各社の公式ページから取得し、Vultrの利用規約だけは公式サイトが応答しなかったため、2026年8月17日のWayback Machineの記録を読んだ。

専有サーバーの出典は次のとおりである。

- [Hetzner AMD Processors Server](https://www.hetzner.com/dedicated-rootserver/matrix-ax/)
- [Hetzner Intel Processors Server](https://www.hetzner.com/dedicated-rootserver/matrix-ex/)
- [Hetznerのサーバーオークションのデータ](https://www.hetzner.com/_resources/app/data/app/live_data_sb.json)
- [netcup Root Server](https://www.netcup.com/en/server/root-server)
- [OVHcloud US Rise](https://eco.us.ovhcloud.com/rise/)
- [OVHcloud USの専有サーバーのカタログAPI](https://api.us.ovhcloud.com/v1/order/catalog/public/eco?ovhSubsidiary=US)
- [OVHcloud USの在庫API](https://api.us.ovhcloud.com/v1/dedicated/server/datacenter/availabilities)
- [OVHcloud US Dedicated Servers FAQ](https://us.ovhcloud.com/bare-metal/faq/)
- [Contabo Cloud VDS](https://contabo.com/en/vds/)

共有vCPUのVPSの出典は次のとおりである。

- [OVHcloud USのVPSのカタログAPI](https://api.us.ovhcloud.com/1.0/order/catalog/public/vps?ovhSubsidiary=US)
- [Contabo Cloud VPS 12](https://contabo.com/en/vps/cloud-vps-core-12)
- [netcup VPS](https://www.netcup.com/en/server/vps)
- [Hetzner Cloud](https://www.hetzner.com/cloud/)
- [Hetznerの2026年6月15日の価格改定](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
- [VultrのプランAPI](https://api.vultr.com/v2/plans)
- [Linodeのインスタンス種別API](https://api.linode.com/v4/linode/types)
- [DigitalOcean Droplet Pricing](https://www.digitalocean.com/pricing/droplets)
- [ABLENET VPS 料金](https://www.ablenet.jp/vps/service/plan_fee.html)
- [XServer VPS 料金](https://vps.xserver.ne.jp/price.php)
- [ConoHa VPS 料金](https://vps.conoha.jp/pricing/)
- [KAGOYA 新規申込の停止のお知らせ](https://www.kagoya.jp/news/2026101937082/)
- [vpsbenchmarks.com](https://www.vpsbenchmarks.com/trials/)

規約と仕様の出典は次のとおりである。

- [netcup General Terms and Conditions](https://www.netcup.com/en/terms-and-conditions)
- [netcup Root Server vs. VPS](https://www.netcup.com/en/blog/root-server/root-server-vs-vps-which-fits-your-project)
- [Contabo Terms and Conditions](https://contabo.com/en/legal/terms-and-conditions/)
- [Akamai: How to choose a compute instance plan](https://techdocs.akamai.com/cloud-computing/docs/how-to-choose-a-compute-instance-plan)
- [Vultr Acceptable Use Policy（2026年8月17日の記録）](http://web.archive.org/web/20260817184054/https://www.vultr.com/legal/use-policy/)
- [DigitalOcean: Choosing a Droplet plan](https://docs.digitalocean.com/products/droplets/concepts/choosing-a-plan/)
- [DigitalOcean Acceptable Use Policy](https://www.digitalocean.com/legal/acceptable-use-policy)
- [さくらのVPS 約款](https://www.sakura.ad.jp/agreement/[a]yakkan2_vps.pdf)
- [さくらのVPS リソース制限](https://manual.sakura.ad.jp/vps/support/technical/resource-limit.html)
- [ConoHa 会員規約](https://www.conoha.jp/agreement/)
- [XServer VPS 利用規約](https://vps.xserver.ne.jp/rule/rule.php)
- [ABLENET 利用規約](https://www.ablenet.jp/company/kiyaku.html)

専有vCPUのクラウドとクレジット型の出典は次のとおりである。

- [Oracle Cloudの料金API](https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/?currencyCode=USD)
- [Oracle Cloud Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)
- [Oracle Cloud Compute Shapes](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm)
- [さくらのクラウド コア専有プラン](https://cloud.sakura.ad.jp/products/server/dedicated-core/)
- [AWS: Key concepts for burstable performance instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html)
- [Lightsail: Baseline CPU performance](https://docs.aws.amazon.com/lightsail/latest/userguide/baseline-cpu-performance.html)
- [Azure Basv2 series](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/basv2-series)
- [Azureの小売価格API](https://prices.azure.com/api/retail/prices)
- [Google Cloud General-purpose machine pricing](https://cloud.google.com/products/compute/pricing/general-purpose)
