FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      octave gfortran gcc g++ make cargo \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN for d in submotors/*/; do (cd "$d" && cargo build --release) || true; done

RUN useradd -m app && chown -R app /app
USER app

ENV PORT=8000
EXPOSE 8000
CMD ["python3", "http_gateway.py"]
