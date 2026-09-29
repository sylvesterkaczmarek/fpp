from pathlib import Path
import os, re, shutil, subprocess, hashlib, json

root = Path.cwd()
src = root / "fpp"
logs = root / "validation-logs"
logs.mkdir(exist_ok=True)
base = "695e2a8dc544e3d52aaf612631abe604dcbe36b3"
paths = ["compiler/lib/src/main/scala/codegen/CppWriter/TopologyCppWriter/TopConfigObjects.scala",
         "compiler/lib/src/main/scala/codegen/CppWriter/TopologyCppWriter/TopConstants.scala",
         "compiler/lib/src/main/scala/codegen/CppWriter/TopologyCppWriter/TopHelperFns.scala"]

def run(name, args, cwd, expect=0):
    p = subprocess.run(args, cwd=cwd, capture_output=True)
    text = (p.stdout + p.stderr).decode(errors="replace")
    (logs / (name + ".log")).write_text(text)
    if expect == "failure":
        assert p.returncode != 0, name + " unexpectedly passed"
    else:
        assert p.returncode == expect, name + "\n" + text[-4000:]
    print(name, "EXPECTED FAILURE" if expect == "failure" else "PASS", flush=True)
    return text

launcher = root / "sbt-launch.jar"
assert hashlib.sha256(launcher.read_bytes()).hexdigest() == "e988d533a020e5b60ec22c3b5df4cd3e3df465f4fdc3951c63036e21483978e4"
sbt = ["java", "-Xmx3G", "-Xss8M", "-Dsbt.supershell=false", "-Dsbt.log.noformat=true", "-jar", str(launcher)]
built = run("scala-and-assembly", sbt + ["test", "assembly"], src / "compiler")
assert "succeeded 689, failed 0" in built
bin_dir = src / "compiler/bin"
bin_dir.mkdir(exist_ok=True)
built_jar = src / "compiler/tools/fpp/target/scala-3.9.0/fpp-assembly-0.1.0-SNAPSHOT.jar"
shutil.copy2(built_jar, bin_dir / "fpp.jar")
for tool in (src / "compiler/tools.txt").read_text().split():
    p = bin_dir / ("fpp-" + tool)
    p.write_text('#!/bin/sh\nexec java --sun-misc-unsafe-memory-access=allow --enable-native-access=ALL-UNNAMED -jar "$(dirname "$0")/fpp.jar" ' + tool + ' "$@"\n')
    p.chmod(0o755)
os.environ["FPRIME"] = str(root / "fprime")
top = src / "compiler/tools/fpp-to-cpp/test/top"
cli = run("all-cpp-generator-tests", ["./test"], top.parent)
assert "All tests" in cli and "FAILED" not in cli
assert sum(map(int, re.findall(r"^(\d+) passed$", cli, re.M))) == 139
cpp = run("all-topology-cpp-checks", ["./check-cpp"], top)
print("C++ check configurations:", cpp.count("variable_flags="), flush=True)
fixed_sources = {p: (src / p).read_bytes() for p in paths}
fixed_jar = (bin_dir / "fpp.jar").read_bytes()
case = top / "check-cpp-dir/basic"
try:
    for p in paths:
        (src / p).write_bytes(subprocess.check_output(["git", "show", base + ":" + p], cwd=src))
    run("original-generator-build", sbt + ["assembly"], src / "compiler")
    shutil.copy2(built_jar, bin_dir / "fpp.jar")
    failure = run("original-generator-cpp-regression", ["./check"], case, expect="failure")
    assert (" X" in failure or " x" in failure) and "error:" in failure
finally:
    for p, data in fixed_sources.items():
        (src / p).write_bytes(data)
    (bin_dir / "fpp.jar").write_bytes(fixed_jar)
restored = run("restored-cpp-regression", ["./check"], case)
assert restored.count("variable_flags=") == 8
run("clean-source", ["git", "diff", "--exit-code"], src)
print("689 Scala tests, 139 C++ generator cases, full topology compile checks, and the before/after regression verified.", flush=True)
