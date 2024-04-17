FROM python:3.11.5

WORKDIR /wise_app

RUN apt-get update && apt-get install -y \
#    xdg-utils \
#    chromium \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY *.py .
COPY .streamlit/ .streamlit/
COPY run_app.sh .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8501

ENTRYPOINT ["./run_app.sh"]