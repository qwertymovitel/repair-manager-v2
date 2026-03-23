FROM python:3.9-slim

WORKDIR /app

# Install dependencies first (better for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Ensure the instance folder exists and has write permissions
RUN mkdir -p /app/instance && chmod 777 /app/instance

EXPOSE 5000

CMD ["python", "app.py"]
