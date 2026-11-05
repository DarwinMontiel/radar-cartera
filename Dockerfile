# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY --from=build /wheels /wheels
RUN pip install /wheels/*.whl && rm -rf /wheels \
    && useradd --create-home --uid 10001 etl
USER etl
WORKDIR /home/etl
ENTRYPOINT ["cartera"]
CMD ["--help"]
