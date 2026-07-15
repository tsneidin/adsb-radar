FROM python:3-alpine
WORKDIR /app
COPY radar.html server.py /app/
EXPOSE 8080
CMD ["python", "server.py"]
