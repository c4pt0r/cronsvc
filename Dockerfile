FROM python:3.11-slim-buster
WORKDIR /app

COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 9002 

CMD ["python", "main.py", "--host=0.0.0.0", "--port=9002"]
