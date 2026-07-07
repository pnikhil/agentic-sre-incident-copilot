FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Kindly note that profiles/ and data/ are read at runtime, so the same are copied in.
COPY pyproject.toml README.md ./
COPY aegis ./aegis
COPY demoapp ./demoapp
COPY data ./data
COPY profiles ./profiles
COPY tests ./tests

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[dev,demo]"

CMD ["python", "-m", "aegis.cli", "run", "--scenario", "bad_deploy"]
