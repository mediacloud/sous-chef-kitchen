FROM prefecthq/prefect:3.3.1-python3.10
COPY . /opt/prefect/sous-chef-kitchen/
WORKDIR /opt/prefect/sous-chef-kitchen/
