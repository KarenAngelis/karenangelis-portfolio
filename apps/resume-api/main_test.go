package main

import (
    "net/http/httptest"
    "testing"
)

func TestProfileContract(t *testing.T) {
    h:=handler([]byte(`{"name":"Karen Angelis"}`))
    req:=httptest.NewRequest("GET","/api/profile",nil)
    req.Header.Set("Origin","http://localhost:4173")
    res:=httptest.NewRecorder()
    h.ServeHTTP(res,req)
    if res.Code!=200 || res.Body.String()!=`{"name":"Karen Angelis"}` { t.Fatal("invalid profile response") }
    if res.Header().Get("Access-Control-Allow-Origin")!="http://localhost:4173" { t.Fatal("local browser origin missing") }
    req=httptest.NewRequest("POST","/api/profile",nil)
    res=httptest.NewRecorder()
    h.ServeHTTP(res,req)
    if res.Code!=405 { t.Fatal("profile must be read-only") }
}
