FROM python@sha256:9381e50cc82f4279b949fcd2d2f5e57cf97b1da2399eb956502364ceea2f4e83
COPY honest_repair.py shortcut_probe.py /opt/scopebreak/
RUN addgroup -S scopebreak && adduser -S -G scopebreak -h /workspace agent
USER agent
WORKDIR /workspace/app
