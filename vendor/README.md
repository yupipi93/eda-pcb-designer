# vendor/ — external binaries used by the autorouter pipeline

`freerouting.jar` is **not committed** (it's a 64 MB binary). Fetch it once
per clone with the pinned, checksum-verified script:

```bash
./vendor/fetch-freerouting.sh
# → downloads freerouting v2.1.0 from the official GitHub releases,
#   verifies its SHA-256, installs it as vendor/freerouting.jar
```

The `route` pipeline stage fails fast with the same download instructions if
the JAR is missing.

## freerouting.jar

Open-source autorouter (Java) used by the `route` stage (see
[`src/pcb_designer/autorouter.py`](../src/pcb_designer/autorouter.py) and the
worked example [`projects/mt1/tools/run_autorouter.py`](../projects/mt1/tools/run_autorouter.py)).
Pinned at **v2.1.0** (April 2025),
sha256 `2c07d58f75dac03782664081e7a58b41c25400d871a9fcf166a2ea6fe60d5def`.
Upstream repo: https://github.com/freerouting/freerouting

To bump the version later: update `VERSION` and `SHA256` in
[`fetch-freerouting.sh`](fetch-freerouting.sh) and re-run it.

### Java requirement (must install once per machine)

freerouting v2.x requires **Java 21+**. On Ubuntu / Debian:

```bash
sudo apt install -y openjdk-21-jre-headless
```

macOS:

```bash
brew install openjdk@21
```

The autorouter wrapper (`pcb_designer.autorouter.find_java21`) auto-detects
the JRE at common paths (`/usr/lib/jvm/java-21-openjdk-amd64/bin/java`,
`/usr/lib/jvm/temurin-21-jdk-amd64/bin/java`,
`/opt/homebrew/opt/openjdk@21/bin/java`). Add your own path to the
candidates list if needed — it doesn't change the system default.

## Verify

```bash
java -jar vendor/freerouting.jar --help    # should print the v2.1.0 banner
```
