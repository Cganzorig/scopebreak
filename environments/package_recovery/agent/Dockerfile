FROM python@sha256:9381e50cc82f4279b949fcd2d2f5e57cf97b1da2399eb956502364ceea2f4e83
RUN addgroup -S workspace && adduser -S -G workspace -h /workspace operator
USER operator
WORKDIR /workspace/app
