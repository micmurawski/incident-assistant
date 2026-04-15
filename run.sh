#export DOCKER_HOST=unix:///var/run/docker.sock
set -e
for i in {1..5}; do echo "--- Starting Run $i ---" | tee -a output.log; python3 -u agent/episodes_runner/experiment_runner.py 2>&1 | tee -a output.log; done
