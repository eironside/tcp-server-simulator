FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
COPY scripts /app/scripts
COPY configs /app/configs
COPY data /app/data

RUN python -m pip install --upgrade pip && \
    pip install -e .

CMD ["python", "-m", "tcp_sim", "--headless"]
