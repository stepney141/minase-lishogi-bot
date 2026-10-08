# AWS運用費用の比較

2026年9月22日にAWSの公式資料と公開料金データを確認した。
24時間常駐し、対局中の中断を避けるという条件では、まずEC2のオンデマンドで性能を測り、構成が固まってから1年のSavings Plansを検討する。
リージョンは限定せず、Armへの移行はx86から対局性能を落とさないことを採用条件とする。
安価であっても性能が低下する構成は採用しない。
以下の料金表は候補比較のための試算であり、このエンジンの性能測定結果ではない。

## 東京の月額試算

試算はLinux、共有テナンシー、追加ソフトウェアなし、月730時間の稼働を前提とする。
各月額には、gp3ストレージ20 GBとパブリックIPv4アドレス1個を含めた。
税金、送信データ、外部サービスへのログ保管、スナップショット、有料サポートは含めず、無料枠とクレジットも適用していない。

計算には[AWS Price Listの東京EC2料金表](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-northeast-1/index.csv)を用いた。
取得した料金表の公開日時は2026年9月21日19:47:12 UTC、版は`20260921194712`、対象レコードの発効日は2026年9月1日である。
抽出条件は`TermType=OnDemand`、`Tenancy=Shared`、`Operating System=Linux`、`Pre Installed S/W=NA`、`CapacityStatus=Used`であり、以下の仮想CPU数とメモリ容量も同じデータで確認した。

| インスタンス | 仮想CPU数 | 物理コア数 | メモリ | EC2単価 USD/時間 | 月額合計 USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| c8a.large | 2 | 2 | 4 GiB | 0.13566 | 104.60 |
| c8a.xlarge | 4 | 4 | 8 GiB | 0.27132 | 203.63 |
| c8a.2xlarge | 8 | 8 | 16 GiB | 0.54264 | 401.70 |
| c8g.large | 2 | 2 | 4 GiB | 0.10006 | 78.61 |
| c8g.xlarge | 4 | 4 | 8 GiB | 0.20012 | 151.66 |
| c8g.2xlarge | 8 | 8 | 16 GiB | 0.40024 | 297.75 |
| c9g.large | 2 | 2 | 4 GiB | 0.10906 | 85.18 |
| c9g.xlarge | 4 | 4 | 8 GiB | 0.21812 | 164.80 |
| c9g.2xlarge | 8 | 8 | 16 GiB | 0.43624 | 324.03 |

gp3は東京で0.096 USD/GB月なので、20 GBで1.92 USD/月となる。
パブリックIPv4アドレスは0.005 USD/時間なので、730時間で3.65 USDとなり、表の計算式は「EC2単価 × 730 + 1.92 + 3.65」である。
ストレージを10 GBにすると月額は0.96 USD下がるが、イメージ、ログ、更新時の空き容量を先に確認する。
gp3の標準性能は毎秒3,000回の入出力操作と125 MB/sの転送速度を含み、表では追加性能を購入していない。
AWSのEBS料金表では1 GBを1,024³バイトと定義している。
根拠は[東京EC2料金表](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-northeast-1/index.csv)、[EBS料金](https://aws.amazon.com/ebs/pricing/)、[IPv4料金](https://aws.amazon.com/vpc/pricing/)である。

## CPUの比較条件

C7a、C8a、C7g、C8g、C9gでは、仮想CPU1個が物理コア1個に対応する。
対してC7iとC8iでは、通常は同時マルチスレッディングにより1物理コアを2個の仮想CPUとして提供するため、たとえば`c8i.2xlarge`は8仮想CPUでも物理コアは4個である。
探索の処理量はコア数だけでは決まらないため、同じ局面と持ち時間を使って比較する必要がある。
物理コア数の根拠は[AWSの計算最適化インスタンス仕様](https://docs.aws.amazon.com/ec2/latest/instancetypes/co.html)である。

C8aはx86-64なので既存のamd64構成を出発点にできるが、C8gとC9gはArm向けのビルドと動作確認が必要になる。
東京のC8a料金は同サイズのC7aより5%高く、AWSはC7a比で最大30%の性能向上を公表している。
C9gはC8gより約9%高く、AWSはC8g比で最大25%の性能向上を公表している。
これらはAWSの一般的な比較値であり、この将棋エンジンでの改善率は未確認なので、候補を絞る根拠として使う。
東京での提供開始日はC8aが2026年3月18日、C9gが2026年9月3日である。
根拠は[C8aの東京提供開始](https://aws.amazon.com/about-aws/whats-new/2026/03/amazon-ec2-r8a-instances-asia-pacific-tokyo-regions/)、[C9gの東京提供開始](https://aws.amazon.com/about-aws/whats-new/2026/09/ec2-c9g-c9gd-asia-pacific-tokyo/)である。

比較用に確認した他の候補も同じ条件で計算した。
以下の価格は[東京EC2料金表](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-northeast-1/index.csv)に基づく。

| インスタンス | 物理コア数 | メモリ | EC2単価 USD/時間 | 月額合計 USD |
| --- | ---: | ---: | ---: | ---: |
| c7a.xlarge | 4 | 8 GiB | 0.25840 | 194.20 |
| c7a.2xlarge | 8 | 16 GiB | 0.51680 | 382.83 |
| c7i.xlarge | 2 | 8 GiB | 0.22470 | 169.60 |
| c7i.2xlarge | 4 | 16 GiB | 0.44940 | 333.63 |
| c8i.xlarge | 2 | 8 GiB | 0.23594 | 177.81 |
| c8i.2xlarge | 4 | 16 GiB | 0.47188 | 350.04 |
| c7g.xlarge | 4 | 8 GiB | 0.18190 | 138.36 |
| c7g.2xlarge | 8 | 16 GiB | 0.36380 | 271.14 |
| c8gn.xlarge | 4 | 8 GiB | 0.29840 | 223.40 |
| c8gn.2xlarge | 8 | 16 GiB | 0.59690 | 441.31 |

## リージョンの比較

lishogiは2026年3月4日の[公式告知](https://lishogi.org/blog/post/aZ10yRIAACsA2sRy)で、メインサーバーを欧州から米国西部へ移転したと説明している。
同告知には具体的な都市やクラウド事業者の記載がないため、AWSのオレゴンに置けば最短距離になるとは断定できないが、料金と応答時間を比較する際の有力な候補になる。
各リージョンから実際のAPI応答時間はまだ測定していない。

オレゴンと北バージニアでは、主要候補のオンデマンド単価が東京より約20%低い。
現行の同時2局に合わせた物理8コア、16 GiBの候補について、Linux、月730時間、gp3 20 GB、IPv4アドレス1個で比較した。
月額の単位はUSDで、税金と通信量などの除外条件は東京の試算と共通である。

| リージョン | c8a.2xlarge | c8g.2xlarge | c9g.2xlarge |
| --- | ---: | ---: | ---: |
| オレゴン us-west-2 | 319.94 | 238.15 | 259.11 |
| 北バージニア us-east-1 | 319.94 | 238.15 | 259.11 |
| 北カリフォルニア us-west-1 | 提供なし | 295.00 | 提供なし |
| 東京 ap-northeast-1 | 401.70 | 297.75 | 324.03 |

オレゴンと北バージニアのEC2時間単価は、C8aが0.43108 USD、C8gが0.31904 USD、C9gが0.34776 USDである。
両リージョンのgp3単価は0.08 USD/GB月なので、月額には1.60 USDのストレージ料金と3.65 USDのIPv4料金を加えた。
北カリフォルニアのC8g時間単価は0.39648 USD、gp3単価は0.096 USD/GB月であり、C8aとC9gは[公式の提供リージョン一覧](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-regions.html)にない。

追加調査では、全インスタンスの料金表を取得する代わりに、AWS公開データの[オレゴンのLinux料金](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20West%20%28Oregon%29/Linux/index.json)、[北カリフォルニアのLinux料金](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/US%20West%20%28N.%20California%29/Linux/index.json)、[EBS料金](https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ebs.json)を確認した。
これらの公開日時は2026年9月21日19:47:12 UTCで、北バージニアには取得済みの[公式EC2料金表](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.csv)を用いた。
今回の比較範囲では、x86の初期候補をオレゴンの`c8a.2xlarge`とし、Armは同じリージョンの最適化したx86版を性能で下回らないと実測できた場合に採用する。

## 契約と中断

継続稼働の料金を下げるには、性能と稼働量を確認した後にSavings Plansを検討する。
1年または3年にわたり時間当たりの支出を約束するため、稼働を減らしても契約上の支払いが残る。
Compute Savings Plansはインスタンスの系列やリージョンを変更しやすく、EC2 Instance Savings Plansは特定の系列とリージョンに適用されるため、たとえばC8gからC9gへの移行を予定するなら条件を区別する。
Savings Plans自体には実行容量の予約は含まれず、Spot料金にも適用されない。
具体的な割引単価は今回取得していない。
根拠は[AWSの購入方式ガイド](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/ec2-purchasing-options-aws-how-to-choose.html)と[Savings Plansの比較](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-ris.html)である。

SpotはAWSが実行容量を回収する際に中断されるため、今回の対局用の推奨構成から外す。
停止または終了の通知は通常2分前だが、通知はベストエフォートである。
根拠は[Spot中断通知の仕様](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/spot-instance-termination-notices.html)である。
参考として取得した[公式Spot公開データ](https://website.spot.ec2.aws.a2z.com/spot.json)の最終更新日時は2026年9月22日00:16:25 UTCで、東京のLinux料金は`c8a.xlarge`が0.0984 USD/時間、`c8g.xlarge`が0.1107 USD/時間、`c9g.xlarge`が0.0845 USD/時間だった。
[公式料金ページ](https://aws.amazon.com/ec2/spot/pricing/)は、この値をリージョン内の最安値と説明しており、月額を保証する値でもアベイラビリティーゾーン別の平均値でもない。

## このリポジトリに適した構成

配備リポジトリのコミット`b1a23e0b2e7ac2bc0369c9d8f88b1cad86324116`では、[config.yml](../../config.yml)が1局4スレッド、置換表2,048 MiB、同時2局、相手の手番中の先読みを指定している。
対局中には合計8探索スレッドが動き得るため、初期候補を物理8コアの`c8a.2xlarge`とする。
置換表は2局で4 GiBとなり、[.env.example](../../.env.example)のコンテナ上限は6 GiBである。
16 GiBのホストならOSなどの余裕も取れるが、この判断は設定値に基づき、実使用量は未測定である。
同時1局で足りる場合は`challenge.concurrency=1`とCPU上限4を組み合わせ、4コアのxlargeへ縮小すると、1局あたりの割当を保ったまま計算機料金を半減できる。

EC2上でDocker ComposeのBotコンテナを1個動かし、gp3 20 GBをOS、イメージ、容量を制限したログに使う構成を推奨する。
イメージを別のビルド環境で作る前提の容量であり、運用機でビルドする場合はビルドキャッシュも含めて容量を見直す。
パブリックサブネットにIPv4アドレスを付け、インターネットゲートウェイ経由でlishogiへ外向きに接続すれば、NATゲートウェイを用意する必要がない。
受信規則を閉じ、必要なエージェントと権限を設定したSession Managerで管理する。
この通信方式の根拠は[インターネットゲートウェイの仕様](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html)と[Session Managerの仕様](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)である。

対局中のCPU負荷が持続するため、T系のバースト性能より計算向けのC系を優先する。
T系のUnlimitedモードでは、一定期間の平均使用率が基準を超えると追加料金が生じるため、対局の多い運用では表示単価だけで比較できない。
対局がまれな場合は別途比較の余地があるが、今回は高負荷時にも性能を維持する構成を選ぶ。
課金条件は[AWSのUnlimitedモードの説明](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode.html)に基づく。

対局中断を減らすには、EC2の自動復旧が有効であること、ホスト再起動後にDockerとBotが起動すること、ログがディスクを埋めないことを確認する。
[compose.yml](../../compose.yml)には`restart: unless-stopped`があるが、プロセスが生存したまま対局受付が止まる状態は再起動設定だけでは検知できないため、受付ループの異常も監視対象にする。
DockerのログとBot自身のログファイルは別々に容量を管理し、更新は進行中の対局が終わってから行う。
同じBotアカウントを複数コンテナで同時に動かさないという[READMEの運用条件](../../README.md)を守る。
EC2の自動復旧は再起動を伴うため、1台構成で障害時の対局継続までは保証できない。
根拠は[EC2の自動復旧](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-recover.html)と[Dockerのログ管理](https://docs.docker.com/engine/logging/configure/)である。

## 機種を決めるための測定

比較基準は、現在の同時2局、1局4スレッド、先読み有効という条件を維持した`c8a.2xlarge`上のx86版とする。
Arm版は、この基準を満たした構成の中で費用を下げられる場合に採用する。
同じ時間内に指す対局なので、単位料金あたりの処理量が増えても、1局の探索が遅くなれば条件を満たさない。
この基準はAWSの候補機間の比較であり、現在のローカル運用機との同等性を意味しない。

現在の[Dockerfile](../../Dockerfile)は`RUSTFLAGS="-C target-cpu=x86-64"`を指定しており、運用先CPUに特化したコード生成を使っていない。
運用先と同じCPUのビルド環境で`target-cpu=native`を指定した版を比較する価値があるが、速度改善率は未測定である。
Armの採否では、x86版とArm版の双方で同じminaseコミットとRustの版を使い、それぞれのCPU向けに最適化する。
x86の汎用ビルドだけを基準にしてArmの性能維持を判断しない。
`native`が指定するのはビルドを実行するホストのCPUなので、異なるCPUで作ったイメージをそのまま配布する前提にはしない。
意味は[Rustのコード生成オプション](https://doc.rust-lang.org/rustc/codegen-options/index.html#target-cpu)で確認した。

Gravitonを比較するには、Composeの`platform: linux/amd64`とDockerfileのx86向け指定を変更し、Arm用イメージを作って動作確認する必要がある。
隣接するminaseのコミット`6c5c559a084704d66ff9b5366efa22eb946601fb`を調べた範囲ではx86専用の組み込み命令は見つからなかったが、Armでのビルドと動作は確認していない。
amd64イメージをArm上でエミュレーションする構成は、今回の性能比較に使わない。
コンテナのアーキテクチャ要件は[Dockerの公式説明](https://docs.docker.com/build/building/multi-platform/)に基づく。

候補機では同じminaseコミットを固定し、まず`bench --depth 6 --threads 1 --repetitions 5`を実行し、スレッド数2と4も同条件で比較する。
このコマンドはminase側の`bench`バイナリに対するものであり、現在の配備イメージには含まれていない。
同バイナリは`engine-default`規則と既定の置換表容量を使うため、結果は機種の比較に用い、lishogi運用条件での検証を別に行う。
次に実際の`--rules lishogi`、4スレッド、置換表2,048 MiBで、同時2局相当の探索と先読みを走らせ、到達深さ、処理時間、ピークメモリ、着手の送信余裕を確認する。
複数スレッドでは重複探索などでノード数自体が変わるため、1秒あたりの探索ノード数だけから棋力の優劣は決めない。
局面を序盤、中盤、終盤から選び、候補ごとに反復して、固定深さへの所要時間と同じ思考時間での到達深さを比較する。
平均値だけでなく遅い側の応答も比較し、2局同時の先読みを含む負荷で秒読みの余裕が減らないことを確認する。
ばらつきが大きく劣化の有無を判定できない場合は、性能低下が検出されなかったことを同等性の証拠にせず、x86を採用する。
この測定で確認できるのは対象局面と条件での性能であり、すべての局面での棋力を保証するものではない。
Arm移行後は[ponder_check.py](../../ponder_check.py)も実行し、先読みの的中、外れ、秒読み、および終局時の停止を確認する。

リージョンは運用者の所在地ではなく、費用とlishogiへの着手応答を基に決める。
平均応答時間だけでなく遅い応答も測り、秒読み中に残る余裕と照合する。
[README](../../README.md)が説明する秒読み時の時間管理では、`move_overhead`の増加だけで通信遅延を吸収できない場合があるため、リージョン変更を時計の検証と組み合わせる。

## 未確認の条件

実機での探索速度、1局と2局の同時実行時の処理量、ピーク時のメモリ使用量、Arm版の動作、各リージョンからlishogiへの応答時間は未測定である。
AWSのアカウントごとの利用上限、起動時の空き容量、Savings Plansの実際の割引率も確認していないため、これらを測定または照合してから最終構成を決める。
今回、AWSリソースは作成していない。
