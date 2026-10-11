FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY collectors ./collectors
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "4173"]
