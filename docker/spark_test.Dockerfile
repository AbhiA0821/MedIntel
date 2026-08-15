FROM python:3.12-slim-bookworm

# Install OpenJDK 17
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jdk-headless procps && \
    rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Install PySpark 4.2.0
RUN pip install --no-cache-dir pyspark==4.2.0

WORKDIR /app
