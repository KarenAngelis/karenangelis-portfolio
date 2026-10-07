package main

import (
    "encoding/json"
    "log"
    "net/http"
    "os"
    "time"
)

func handler(profile []byte) http.Handler {
    mux := http.NewServeMux()
    mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        w.Write([]byte(`{"status":"ok"}`))
    })
    mux.HandleFunc("GET /api/profile", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json; charset=utf-8")
        w.Header().Set("Cache-Control", "public, max-age=60")
        w.Write(profile)
    })
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        origin := r.Header.Get("Origin")
        if origin == "http://localhost:4173" || origin == "http://127.0.0.1:4173" || origin == "https://karenangelis.com" || origin == "https://www.karenangelis.com" {
            w.Header().Set("Access-Control-Allow-Origin", origin)
            w.Header().Set("Vary", "Origin")
        }
        mux.ServeHTTP(w,r)
    })
}

func main() {
    path := os.Getenv("PROFILE_PATH")
    if path == "" { path = "../../web/data/profile.json" }
    profile, err := os.ReadFile(path)
    if err != nil { log.Fatal(err) }
    if !json.Valid(profile) { log.Fatal("profile.json inválido") }
    server := &http.Server{Addr: ":8080", Handler: handler(profile), ReadHeaderTimeout: 5*time.Second, WriteTimeout: 10*time.Second, IdleTimeout: 60*time.Second}
    log.Println("API Go em :8080")
    log.Fatal(server.ListenAndServe())
}
