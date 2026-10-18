FROM python:3.12-slim
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir '.[test]' && playwright install --with-deps chromium --only-shell
COPY alembic.ini ./
COPY alembic ./alembic
COPY tests ./tests
RUN mkdir -p /data
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
