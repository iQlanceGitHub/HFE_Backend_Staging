FROM python:3.11-slim-bookworm AS fast-api

RUN adduser --system --no-create-home nonroot

# prepare app directory
RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app


# install project dependencies
COPY pyproject.toml ./
COPY Makefile Makefile
COPY .env ./

RUN pip3 install --no-cache-dir --upgrade pip setuptools
# Install make
RUN apt-get update && apt-get install -y build-essential && apt-get clean && rm -rf /var/lib/apt/lists/*


RUN make install_on_docker
COPY avatars avatars/
COPY src src/

EXPOSE		8100

RUN mkdir -p /nonexistent
RUN chown -R nonroot /usr/src/app
RUN chown -R nonroot /nonexistent
RUN mkdir -p /home/nonroot
RUN chown -R nonroot /home/nonroot
USER nonroot
