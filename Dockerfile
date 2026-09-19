# syntax=docker/dockerfile:1
# minase を lishogi の Bot アカウントとして動かすイメージ。
# minase のソースは compose.yml の additional_contexts が名前付き文脈
# minase-source として渡す(minase-gui と同じ方式)。

FROM rust:1.98-bookworm AS minase-build
WORKDIR /build/minase
COPY --from=minase-source / ./
ENV RUSTFLAGS="-C target-cpu=x86-64"
RUN cargo build --locked --release --bin minase

FROM python:3.11-slim-bookworm AS runtime
# stepney141/lishogi-bot の固定コミット(2026年9月19日)。nhamil/lishogi-bot db18bd2 に
# ponder の修正を 1 コミット加えたフォークである。nhamil 版は TheYoBots/Lishogi-Bot 17c16bc の
# フォークで、lishogi が挑戦 JSON から speed を削った(2025年11月7日 ee46131)ことに
# 追従している(README.md「構成」)。
ARG LISHOGI_BOT_COMMIT=1cbfcb9848dd1ec52ae9ecb1ebe9bafe05ec77ec
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git clone https://github.com/stepney141/lishogi-bot /opt/lishogi-bot \
    && git -C /opt/lishogi-bot checkout --detach "$LISHOGI_BOT_COMMIT" \
    && pip install --no-cache-dir -r /opt/lishogi-bot/requirements.txt \
    && apt-get purge -y git && apt-get autoremove -y \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /var/log/lishogi-bot && chown app /var/log/lishogi-bot
COPY --from=minase-build /build/minase/target/release/minase /opt/minase/minase
COPY minase-lishogi /opt/minase/minase-lishogi
# 設定ファイルはイメージへ入れず、compose.yml が config.yml を
# /opt/lishogi-bot/config.yml へ読み取り専用でマウントする。
WORKDIR /opt/lishogi-bot
USER app
# 認証トークンは実行時に環境変数 LISHOGI_BOT_TOKEN で渡す。
ENTRYPOINT ["python3", "lishogi-bot.py"]
CMD ["-v", "--logfile", "/var/log/lishogi-bot/lishogi-bot.log"]
