FROM python@sha256:9381e50cc82f4279b949fcd2d2f5e57cf97b1da2399eb956502364ceea2f4e83
COPY server.py /opt/scopebreak/server.py
RUN addgroup -S scopebreak && adduser -S -G scopebreak -h /workspace app && mkdir -p /workspace/app /telemetry && chown -R app:scopebreak /workspace /telemetry
USER app
EXPOSE 8080
CMD ["python", "/opt/scopebreak/server.py"]
