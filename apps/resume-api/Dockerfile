FROM golang:1.26-alpine AS build
WORKDIR /src
COPY apps/resume-api/ .
RUN go test ./... && CGO_ENABLED=0 go build -o /resume-api .
FROM scratch
COPY --from=build /resume-api /resume-api
COPY web/data/profile.json /profile.json
ENV PROFILE_PATH=/profile.json
USER 65534:65534
ENTRYPOINT ["/resume-api"]
