FROM python:3.12-slim
WORKDIR /app
RUN pip install flask==3.1.1
COPY app.py .
COPY templates/ templates/
CMD ["python", "app.py"]
