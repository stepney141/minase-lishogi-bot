# syntax=docker/dockerfile:1
# minase を lishogi の Bot アカウントとして動かすイメージ。
# minase は crates.io の公開版をビルドし、Lishogi-Bot のソースは compose.yml の
# additional_contexts から渡す。

FROM rust:1.98-bookworm AS minase-build
# target-cpu=native はビルド機の CPU に特化するので、運用機でビルドする。
# crates.io の crate には minase のワークスペースの release プロファイルが入らないため、
# 同じ LTO と codegen-units を環境変数で与える。
ENV RUSTFLAGS="-C target-cpu=native" \
    CARGO_PROFILE_RELEASE_LTO=true \
    CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1
RUN cargo install minase --version =2.0.0 --locked --bin minase --root /build

FROM python:3.11-slim-bookworm AS runtime
# 実行に必要なソースだけを取り込み、隣のリポジトリの設定や認証情報は含めない。
COPY --from=lishogi-bot-source /requirements.txt /opt/lishogi-bot/requirements.txt
RUN pip install --no-cache-dir -r /opt/lishogi-bot/requirements.txt \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /var/log/lishogi-bot && chown app /var/log/lishogi-bot
COPY --from=lishogi-bot-source /*.py /opt/lishogi-bot/
COPY --from=lishogi-bot-source /engine_ctrl /opt/lishogi-bot/engine_ctrl
COPY --from=minase-build /build/bin/minase /opt/minase/minase
COPY minase-lishogi /opt/minase/minase-lishogi
# 設定ファイルはイメージへ入れず、compose.yml が config.yml を
# /opt/lishogi-bot/config.yml へ読み取り専用でマウントする。
WORKDIR /opt/lishogi-bot
USER app
# 認証トークンは実行時に環境変数 LISHOGI_BOT_TOKEN で渡す。
ENTRYPOINT ["python3", "lishogi-bot.py"]
CMD ["-v", "--logfile", "/var/log/lishogi-bot/lishogi-bot.log"]
