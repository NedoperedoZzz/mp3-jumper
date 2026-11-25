FROM python:3.10-slim
WORKDIR /app
RUN apt-get update && apt-get install -y ffmpeg libsndfile1 rubberband-cli
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]