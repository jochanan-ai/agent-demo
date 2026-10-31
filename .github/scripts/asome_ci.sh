#!/usr/bin/env bash
# CI of an agent repository (asome-platform templates/agent-repo, F5): tests with coverage and the
# image build, the same for every stack. Dependencies only verified: Python with hashes (pip
# --require-hashes), Gradle with dependency verification and a checked wrapper, Maven only through
# ./mvnw (Maven >= 3.9 from Maven Central, distributionSha256Sum) with trusted checksums: every
# artifact and plugin must match .mvn/checksums (SHA-512), a missing one fails too (review F5:
# --strict-checksums alone only compares with the repository's own checksum files).
#   asome_ci.sh test DIR OUT     tests of the project in DIR; reports and metrics.json into OUT
#   asome_ci.sh build DIR        docker build of DIR when it has a Dockerfile (nothing is pushed)
set -Eeuo pipefail
shopt -s globstar nullglob

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-}"
dir="$(cd "${2:?project directory}" && pwd)"

stack() {
  if [[ -f "$dir/gradlew" || -f "$dir/build.gradle" || -f "$dir/build.gradle.kts" ]]; then
    echo gradle
  elif [[ -f "$dir/pom.xml" ]]; then
    echo maven
  elif [[ -f "$dir/pyproject.toml" || -f "$dir/requirements-dev.lock" || -f "$dir/requirements.lock" ]]; then
    echo python
  else
    echo none
  fi
}

java_home() {
  # Temurin 21 of the runner image; the build pins the major version (Gradle toolchain, Maven enforcer)
  export JAVA_HOME="${JAVA_HOME_21_X64:-${JAVA_HOME:-}}"
}

collect() {
  # collect OUT PATTERN...: copy the reports the build wrote into OUT/reports
  local out="$1" n=0 f
  shift
  mkdir -p "$out/reports"
  for pattern in "$@"; do
    # shellcheck disable=SC2231  # the pattern is a glob (globstar) on purpose
    for f in "$dir"/$pattern; do
      n=$((n + 1))
      cp "$f" "$out/reports/$n-$(basename "$f")"
    done
  done
}

test_python() {
  local out="$1" lock=""
  for candidate in requirements-dev.lock requirements.lock; do
    if [[ -f "$dir/$candidate" ]]; then lock="$candidate"; break; fi
  done
  [[ -n "$lock" ]] || { echo "Python: chybí requirements-dev.lock nebo requirements.lock (s hashi)"; return 1; }
  python3 -m venv "$out/venv" || return 1
  "$out/venv/bin/pip" install --quiet --require-hashes -r "$dir/$lock" || return 1
  (cd "$dir" && "$out/venv/bin/python" "$here/pycov.py" --junit "$out/reports/junit.xml" --json "$out/coverage.json" -- -q)
}

verify_gradle_wrapper() {
  local props="$1" url version want have
  url="$(sed -n 's/^distributionUrl=//p' "$props" | sed 's/\\:/:/g')"
  [[ "$url" == https://services.gradle.org/distributions/gradle-*.zip ]] || { echo "distributionUrl mimo services.gradle.org: $url"; return 1; }
  version="$(sed -E 's#.*/gradle-(.+)-(bin|all)\.zip$#\1#' <<<"$url")"
  want="$(curl -fsSL "https://services.gradle.org/distributions/gradle-$version-wrapper.jar.sha256")" || return 1
  have="$(sha256sum "$dir/gradle/wrapper/gradle-wrapper.jar" | cut -d' ' -f1)"
  [[ "$want" == "$have" ]] || { echo "gradle-wrapper.jar neodpovídá Gradle $version"; return 1; }
}

test_gradle() {
  local out="$1" props="$dir/gradle/wrapper/gradle-wrapper.properties" status=0
  [[ -f "$dir/gradlew" && -f "$props" ]] || { echo "Gradle jen přes wrapper (gradlew, gradle-wrapper.properties)"; return 1; }
  grep -q '^distributionSha256Sum=' "$props" || { echo "gradle-wrapper.properties bez distributionSha256Sum"; return 1; }
  [[ -f "$dir/gradle/verification-metadata.xml" ]] || { echo "chybí gradle/verification-metadata.xml (ověření závislostí)"; return 1; }
  verify_gradle_wrapper "$props" || return 1
  java_home
  (cd "$dir" && ./gradlew --no-daemon --stacktrace test) || status=$?
  if grep -qs jacoco "$dir"/build.gradle* "$dir"/*/build.gradle*; then
    (cd "$dir" && ./gradlew --no-daemon jacocoTestReport) || status=$((status ? status : 1))
  fi
  collect "$out" '**/build/test-results/test/*.xml' '**/build/reports/jacoco/test/jacocoTestReport.xml'
  return "$status"
}

verify_maven_wrapper() {
  local props="$1" url version
  url="$(sed -n 's/^distributionUrl=//p' "$props" | sed 's/\\:/:/g' | tr -d '[:space:]')"
  version="$(sed -nE 's#^https://repo\.maven\.apache\.org/maven2/org/apache/maven/apache-maven/([0-9]+\.[0-9]+\.[0-9]+)/apache-maven-\1-bin\.(zip|tar\.gz)$#\1#p' <<<"$url")"
  [[ -n "$version" ]] || { echo "distributionUrl mimo Maven Central (apache-maven-<verze>-bin): $url"; return 1; }
  [[ "$(printf '%s\n3.9.0\n' "$version" | sort -V | head -n1)" == 3.9.0 ]] || { echo "Maven $version < 3.9 (důvěryhodné součty)"; return 1; }
  grep -qE '^distributionSha256Sum=[0-9a-f]{64}[[:space:]]*$' "$props" || { echo "maven-wrapper.properties bez distributionSha256Sum"; return 1; }
  [[ ! -e "$dir/.mvn/wrapper/maven-wrapper.jar" && ! -e "$dir/.mvn/wrapper/MavenWrapperDownloader.java" ]] ||
    { echo "Maven wrapper jen typu only-script (bez maven-wrapper.jar)"; return 1; }
}

test_maven() {
  local out="$1" props="$dir/.mvn/wrapper/maven-wrapper.properties" status=0
  [[ -f "$dir/mvnw" && -f "$props" ]] || { echo "Maven jen přes wrapper (mvnw, .mvn/wrapper/maven-wrapper.properties)"; return 1; }
  verify_maven_wrapper "$props" || return 1
  compgen -G "$dir/.mvn/checksums/checksums*.sha512" >/dev/null ||
    { echo "chybí .mvn/checksums/checksums*.sha512 (důvěryhodné součty závislostí)"; return 1; }
  java_home
  # trusted checksums of every resolved artifact (plugins included); the basedir must be absolute
  # (a relative one is taken from the local repository)
  local trusted=(
    --strict-checksums
    -Daether.artifactResolver.postProcessor.trustedChecksums=true
    -Daether.artifactResolver.postProcessor.trustedChecksums.checksumAlgorithms=SHA-512
    -Daether.artifactResolver.postProcessor.trustedChecksums.failIfMissing=true
    -Daether.trustedChecksumsSource.summaryFile=true
    "-Daether.trustedChecksumsSource.summaryFile.basedir=$dir/.mvn/checksums"
  )
  (cd "$dir" && env -u MAVEN_ARGS -u MVNW_REPOURL ./mvnw -B "${trusted[@]}" verify) || status=$?
  collect "$out" '**/target/surefire-reports/TEST-*.xml' '**/target/site/jacoco/jacoco.xml'
  return "$status"
}

case "$cmd" in
  test)
    out="${3:?output directory}"
    mkdir -p "$out/reports"
    out="$(cd "$out" && pwd)"
    kind="$(stack)"
    echo "stack: $kind"
    status=0
    case "$kind" in
      python) test_python "$out" || status=$? ;;
      gradle) test_gradle "$out" || status=$? ;;
      maven) test_maven "$out" || status=$? ;;
      *) echo "no recognised project: no tests" ;;
    esac
    python3 "$here/test_guard.py" summarize "$out" > "$out/metrics.json"
    cat "$out/metrics.json"
    exit "$status"
    ;;
  build)
    if [[ -f "$dir/Dockerfile" ]]; then
      docker build --pull --tag ci-build "$dir"
    else
      echo "no Dockerfile: nothing to build"
    fi
    ;;
  *)
    echo "usage: asome_ci.sh test DIR OUT | build DIR" >&2
    exit 2
    ;;
esac
