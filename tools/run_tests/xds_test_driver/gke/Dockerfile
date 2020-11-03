# Build runtime image.
FROM openjdk:8-jre-alpine

# Copy the compiled files over.
COPY --from=build-env /app/target/ /app/

# Starts java app with debugging server at port 5005.
CMD ["java", "-jar", "/app/hello-world-1.0.0.jar"]
