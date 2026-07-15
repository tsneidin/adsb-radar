FROM python:3-slim
WORKDIR /app
COPY server.py radar.html .
EXPOSE 8080
CMD ["python3", "server.py"]
