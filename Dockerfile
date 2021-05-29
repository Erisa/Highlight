FROM python:3.9-alpine

RUN apk add --no-cache git build-base linux-headers

WORKDIR /usr/src/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "./bot.py"]
