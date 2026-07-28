FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

<<<<<<< HEAD
EXPOSE 5000

CMD [ "sh", "entrypoint.sh" ]
=======
CMD ["python", "app.py"]

EXPOSE 5000

>>>>>>> origin/Hugo

