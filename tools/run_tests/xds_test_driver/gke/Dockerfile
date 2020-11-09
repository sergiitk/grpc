# Build runtime image.
FROM openjdk:10

ENV APP_DIR=/usr/src/app
WORKDIR $APP_DIR

# Install the app
COPY build/install/grpc-interop-testing $APP_DIR/

# Debug logging
COPY assets/logging.properties $APP_DIR/
ENV JAVA_OPTS="-Djava.util.logging.config.file=$APP_DIR/logging.properties"

# Server
CMD ["bin/xds-test-server", "--port=8080"]

# client
# CMD "bin/xds-test-client --server=xds:///{server_uri} --stats_port={stats_port} --qps={qps} {rpcs_to_send} {metadata_to_send}"
