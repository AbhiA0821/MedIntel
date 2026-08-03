FROM apache/airflow:3.0.6

# Install Java because Apache Spark requires JVM
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Return to normal Airflow user
USER airflow

# Python libraries required by MedIntel
RUN pip install --no-cache-dir \
    pyspark==4.1.2 \
    duckdb \
    pandas \
    pyarrow