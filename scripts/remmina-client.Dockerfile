FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential cmake libssl-dev zlib1g-dev libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
# Use Ubuntu's signed source packages so its existing fixes are retained.
RUN sed -i 's/Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update && apt-get install -y --no-install-recommends libgcrypt20-dev libgnutls28-dev \
    && apt-get source libvncserver \
    && cp -a libvncserver-*/. /src/ \
    && test -f libvncclient/rfbproto.c \
    && rm -rf /var/lib/apt/lists/*
COPY remmina-resize.patch remmina-resize-check.c /src/
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
       -DWITH_EXAMPLES=OFF -DWITH_TESTS=OFF -DWITH_GNUTLS=ON -DWITH_GCRYPT=ON -DWITH_SASL=OFF \
    && cmake --build build --target vncclient -j2 \
    && cc -Wall -Wextra -Werror remmina-resize-check.c -I. -Ibuild -Lbuild -Wl,-rpath,/src/build -lvncclient -o /src/check-resize \
    && ! /src/check-resize
RUN patch -p1 < remmina-resize.patch \
    && cmake --build build --target vncclient -j2 \
    && /src/check-resize \
    && LEGION_REMMINA_ZOOM=100 /src/check-resize \
    && LEGION_REMMINA_ZOOM=125 /src/check-resize \
    && LEGION_REMMINA_ZOOM=150 /src/check-resize
CMD ["sh", "-c", "set -eu; staging=$(mktemp -d /out/.export.XXXXXX); trap 'rm -rf \"$staging\"' EXIT; cp -a /src/build/libvncclient.so* \"$staging/\"; chown -R \"$OUTPUT_UID:$OUTPUT_GID\" \"$staging\"; for library in \"$staging\"/*; do mv -Tf \"$library\" \"/out/${library##*/}\"; done"]
