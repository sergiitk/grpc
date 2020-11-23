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
ENTRYPOINT ["bin/xds-test-server"]
