FROM python:3.11-slim

WORKDIR /app

ARG WCF_BUILD_SHA=dev
ENV WCF_BUILD_SHA=${WCF_BUILD_SHA}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
