#!/bin/sh
# 指定コミットの minase を含む lishogi Bot イメージをビルドする。
# 使い方: ./build-image.sh <minaseのコミット>
# minase リポジトリの場所は環境変数 MINASE_REPO で指定する(既定は ../minase)。
# 作業ツリーではなく `git archive` の内容だけをビルド文脈にするため、
# minase の未コミットの変更はイメージへ入らない。イメージは
# minase-lishogi-bot:<完全ハッシュ> と minase-lishogi-bot:latest に付ける。
set -eu
if [ "$#" -ne 1 ]; then
    echo "usage: $0 <minase commit>" >&2
    exit 2
fi
here=$(cd "$(dirname "$0")" && pwd)
minase=${MINASE_REPO:-"$here/../minase"}
commit=$(git -C "$minase" rev-parse --verify "$1^{commit}")
context=$(mktemp)
trap 'rm -f "$context"' EXIT
git -C "$minase" archive --format=tar --prefix=minase/ "$commit" -o "$context"
tar -rf "$context" -C "$here" Dockerfile minase-lishogi
docker build \
    --file Dockerfile \
    --build-arg "MINASE_COMMIT=$commit" \
    --tag "minase-lishogi-bot:$commit" \
    --tag minase-lishogi-bot:latest \
    - < "$context"
echo "built minase-lishogi-bot:$commit"
