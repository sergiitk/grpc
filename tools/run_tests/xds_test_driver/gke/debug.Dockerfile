# Build runtime image.
FROM alpine:latest

ENV APP_DIR=/work
WORKDIR $APP_DIR

RUN apk --no-cache add bash

RUN wget -c https://github.com/fullstorydev/grpcurl/releases/download/v1.6.1/grpcurl_1.6.1_linux_x86_64.tar.gz -O - | tar -xz

# Sleeper
CMD ["/bin/sleep", "inf"]
