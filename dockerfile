FROM python:3.10

# Install system dependencies
RUN apt-get update && \
    apt-get install -y ghostscript libreoffice && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy app code
COPY . .

EXPOSE 5000

# Start the app
CMD ["python", "api.py"]
