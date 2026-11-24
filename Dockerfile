# syntax=docker/dockerfile:1
# minase を lishogi の Bot アカウントとして動かすイメージ。
# minase は crates.io の公開版をビルドし、評価ネットは Hugging Face Hub の固定したリビジョンから
# 取得して SHA-256 を照合する。Lishogi-Bot のソースは compose.yml の additional_contexts から渡す。

FROM rust:1.98-bookworm AS minase-build
# target-cpu=native はビルド機の CPU に特化するので、運用機でビルドする。
# LTO と codegen-units=1 は 2.0.1 以降の crate 自身の release プロファイルが与える。
ENV RUSTFLAGS="-C target-cpu=native"
# minase の版はこの --version の1か所で指定する。
RUN cargo install minase --version =3.0.0 --locked --bin minase --root /build

FROM python:3.11-slim-bookworm AS runtime
# ログはホストの logs/ へ書くので、compose.yml がホストのユーザーの uid と gid を渡す。
ARG APP_UID
ARG APP_GID
# 実行に必要なソースだけを取り込み、隣のリポジトリの設定や認証情報は含めない。
COPY --from=lishogi-bot-source /requirements.txt /opt/lishogi-bot/requirements.txt
RUN pip install --no-cache-dir -r /opt/lishogi-bot/requirements.txt \
    && groupadd --gid ${APP_GID} app \
    && useradd --create-home --uid ${APP_UID} --gid ${APP_GID} app
COPY --from=lishogi-bot-source /*.py /opt/lishogi-bot/
COPY --from=lishogi-bot-source /engine_ctrl /opt/lishogi-bot/engine_ctrl
COPY --from=minase-build /build/bin/minase /opt/minase/minase
COPY minase-lishogi /opt/minase/minase-lishogi
# minase は評価ネットを実行ファイルに埋め込まず、USI のオプション EvalFile で指定したファイルから読む。
# ネットはこの ADD の1か所で指定する(minase の世代反復の第3世代、P 型、規則セット lishogi で学習)。
# 取得したファイルの SHA-256 が一致しなければビルドは失敗する。config.yml の EvalFile は /opt/minase/eval.nnue を指す。
ADD --checksum=sha256:cbbccf6f5ee7097fd890086d2cf4bca72ed969da28353cb0c4a2f4d781acc244 --chmod=644 \
    https://huggingface.co/stepney141/minase-nets/resolve/0a2a688f1ce8cd1dac11ae10cd181e3569410811/nnue/p/minase-nnue-p-lishogi-20261124-cbbccf6f.nnue \
    /opt/minase/eval.nnue
# 設定ファイルはイメージへ入れず、compose.yml が config.yml を
# /opt/lishogi-bot/config.yml へ読み取り専用でマウントする。
WORKDIR /opt/lishogi-bot
USER app
# 認証トークンは実行時に環境変数 LISHOGI_BOT_TOKEN で渡す。
ENTRYPOINT ["python3", "lishogi-bot.py"]
CMD ["-v", "--logfile", "/var/log/lishogi-bot/lishogi-bot.log", "--game-log-dir", "/var/log/lishogi-bot/games"]
