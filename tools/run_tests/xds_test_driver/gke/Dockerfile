# Build runtime image.
FROM openjdk:10
WORKDIR /app
COPY build/install/grpc-interop-testing .

EXPOSE 8080/tcp
CMD ["bin/xds-test-server", "--port=8080"]

# FROM openjdk:8-jre-alpine
# COPY grpc-interop-testing/ /app/
# CMD "bin/xds-test-client --server=xds:///{server_uri} --stats_port={stats_port} --qps={qps} {rpcs_to_send} {metadata_to_send}"

# FROM grpc/java-example-hostname:1.27.0
# EXPOSE 8081/tcp
# CMD ["8081"]
