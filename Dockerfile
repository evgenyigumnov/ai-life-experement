FROM alpine:latest
RUN apk update && apk add bash busybox python3 py3-pip curl vim && \
    # busybox vi не умеет UTF-8 (показывает точки вместо кириллицы),
    # поэтому перекрываем ссылку vi -> vim (/usr/local/bin идёт раньше /bin в PATH)
    ln -sf /usr/bin/vim /usr/local/bin/vi
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8
WORKDIR /root
CMD ["tail", "-f", "/dev/null"]
