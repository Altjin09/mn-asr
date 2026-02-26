FROM python:3.11-slim

# ffmpeg install
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV MODEL_SIZE=large-v3
ENV DEVICE=cpu
ENV COMPUTE=int8
ENV BEAM_SIZE=8
ENV BEST_OF=8

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]