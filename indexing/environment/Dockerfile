FROM elastic/elasticsearch:7.17.28

USER root

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev wget curl \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install \
        pandas pyarrow "elasticsearch>=7.17,<8.0" numpy psutil requests \
    && rm -rf ~/.cache/pip

USER elasticsearch
EXPOSE 9200 9300
CMD ["/usr/share/elasticsearch/bin/elasticsearch"]
