[app]

# App info
title = app2nix
package.name = app2nix
package.domain = com.hitechtn
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,spec,txt,json
source.exclude_patterns = crates/*,tests/*,docs/*,.github/*,scripts/*,static/*,Audit/*,templates/*,translations/*,utils/*
version = 3.1.0

# Requirements
requirements = python3,kivy,certifi,urllib3,charset-normalizer,idna,pydantic,pydantic-settings,typing-extensions,rich,typer,jinja2,httpx
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.arch = arm64-v8a
android.archs = arm64-v8a, armeabi-v7a

# Build
fullscreen = 0
orientation = portrait
adaptation = phone

# Icon and presplash
#icon.filename = %(source.dir)s/assets/icon.png
#presplash.filename = %(source.dir)s/assets/presplash.png

# Log level
log_level = 2

# Source includes
source.include_patterns = assets/*

# Android specific
android.release_artifact = aab
android.enable_androidx = True
android.add_compile_java_api_version = 33

# Gradle dependencies
dependencies = org.jetbrains.kotlin:kotlin-stdlib:1.9.0

# Python package loading
p4a.branch = develop

# Entry point
entry.point = main:app2nixApp

[buildozer]
log_level = 2
warn_on_root = 0
