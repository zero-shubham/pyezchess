FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-compile -r requirements.txt

EXPOSE 8080
CMD ["python", "src/main.py"]
