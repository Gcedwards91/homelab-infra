# CI Self-Healing Loop - PR Specification

**Status:** SHIPPED (Parts 1 and 2). Part 3 (labels) completed as prerequisite.
**Branch target:** `master`
**Estimated scope:** ~2 files modified, ~1 file created

---

## Prioritization Note

This is intentionally implemented before the unit test suite. Once unit tests exist and start failing in CI, the structured issue format (per-service labels, log capture, auto-close workflow) makes those failures easier to track and resolve. Implementing the loop first means the infrastructure is in place when it is first needed.

The service detection in Part 1 uses two passes: one for integration test output (single-quoted container names) and one for unit test output (FAILED lines matched against normalized service terms). Both paths produce per-service labels automatically - no special formatting required in failure messages, only the class/file naming convention in Part 4.

---

## Background Required

Before implementing, read:

- `CLAUDE.md` - architecture, conventions, CI/CD pipeline description
- `.github/workflows/integration-tests.yml` - the existing workflow being modified
- `weather-app/docker-final/tests/test_stack_startup.py` - the test file; note how `pytest.fail(f"'{name}' has...")` messages use single-quoted container names - this feeds Pass 1 of the service detector
- `TESTING_CHECKLIST.md` - full end-to-end test scope; the startup section (1.1–1.4) is the current automated coverage

---

## Summary

Implements a three-part self-healing CI architecture:

1. **Enhanced issue creation** - structured ticket naming, per-service labels, log extraction per failing service, empty output fallback
2. **Targeted test workflow** - parameterized `workflow_dispatch` workflow that runs tests for a specific service in isolation
3. **Auto-close on resolution** - targeted workflow closes single-service issues automatically; STACK issues require manual close after all services verified

```
push → integration tests fail
     → service logs captured to files
     → structured issue opened with service labels and logs
     → developer fixes code
     → developer manually triggers targeted test for that service
     → targeted test passes →
         single-service issue: auto-closed
         STACK issue: comment posted, manual close required
```

---

## Part 1 - Enhanced Issue Creation

### Files to Modify: `.github/workflows/integration-tests.yml`

Two changes: a new log-capture step, and a full replacement of the `Create GitHub issue on test failure` step.

**New step - insert immediately after `Run integration tests`:**

```yaml
- name: Capture service logs on failure
  if: failure()
  working-directory: weather-app/docker-final
  run: |
    mkdir -p /tmp/service-logs
    for service in weather-app statporter prometheus grafana loki promtail alertmanager reverse-proxy demo-container; do
      docker logs $service --tail 50 2>&1 > /tmp/service-logs/${service}.log || echo "no logs available" > /tmp/service-logs/${service}.log
    done
```

**Replacement step - `Create GitHub issue on test failure`:**

The script block goes inside `actions/github-script@v7` with `with: script: |`.

````javascript
const fs = require("fs");

const serviceMap = {
  // terms: normalized strings matched against FAILED lines for unit test detection.
  // Pass 1 matches single-quoted container names ('weather-app') in any output line.
  // Pass 2 matches terms against lowercased FAILED lines (test file paths + class names).
  // reverse-proxy and demo-container need aliases because Python files use underscores
  // and nginx tests may not reference the full container name.
  "weather-app": { prefix: "WA", label: "svc:weather-app", terms: ["weather_app"] },
  statporter: { prefix: "SP", label: "svc:statporter", terms: ["statporter"] },
  prometheus: { prefix: "PROM", label: "svc:prometheus", terms: ["prometheus"] },
  grafana: { prefix: "GRF", label: "svc:grafana", terms: ["grafana"] },
  loki: { prefix: "LOKI", label: "svc:loki", terms: ["loki"] },
  promtail: { prefix: "PT", label: "svc:promtail", terms: ["promtail"] },
  alertmanager: { prefix: "AM", label: "svc:alertmanager", terms: ["alertmanager"] },
  "reverse-proxy": { prefix: "NGX", label: "svc:nginx", terms: ["reverse_proxy", "nginx"] },
  "demo-container": { prefix: "DEMO", label: "svc:demo-container", terms: ["demo_container"] },
};

const rawOutput = fs.existsSync("test-output.txt")
  ? fs.readFileSync("test-output.txt", "utf8")
  : "";

const isEmpty = rawOutput.trim().length === 0;
const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
const shortSha = context.sha.slice(0, 7);
const seq = String(context.runNumber).padStart(4, "0");

let prefix, title, labels, body;

if (isEmpty) {
  prefix = "CI";
  labels = ["test-failure", "ci"];
  title = `[CI-${seq}] test suite failed to launch (commit: ${shortSha})`;
  body = [
    "## CI failure - test output empty",
    "",
    "`pytest` either failed to start or produced no output.",
    "",
    `**Run:** ${runUrl}`,
    `**Commit:** ${shortSha}`,
    "",
    "## To investigate",
    "```",
    "Check the Actions run log directly - no test output was captured.",
    "```",
    "",
    "## To close this issue",
    "1. Fix the underlying CI configuration or environment issue",
    "2. Go to **Actions → targeted-test.yml → Run workflow**",
    "3. Set **Service** to the affected service",
    "4. Set **Issue number** to the issue number shown in the title of this issue",
  ].join("\n");
} else {
  // Pass 1: single-quoted container names in any output line (integration tests)
  const fromContainerNames = new Set(
    Object.entries(serviceMap)
      .filter(([name]) => rawOutput.includes(`'${name}'`))
      .map(([, meta]) => meta.label)
  );

  // Pass 2: FAILED lines matched against normalized terms (unit tests)
  const failedBlock = rawOutput
    .split("\n")
    .filter((l) => l.trimStart().startsWith("FAILED "))
    .join("\n")
    .toLowerCase();

  const fromFailedLines = new Set(
    Object.entries(serviceMap)
      .filter(([, meta]) => meta.terms.some((t) => failedBlock.includes(t)))
      .map(([, meta]) => meta.label)
  );

  const detectedLabels = new Set([...fromContainerNames, ...fromFailedLines]);
  const detectedServices = Object.entries(serviceMap)
    .filter(([, meta]) => detectedLabels.has(meta.label))
    .map(([name, meta]) => ({ name, ...meta }));

  const isStack = detectedServices.length > 1;

  prefix =
    detectedServices.length === 1
      ? detectedServices[0].prefix
      : detectedServices.length > 1
        ? "STACK"
        : "CI";

  labels = ["test-failure", ...detectedServices.map((s) => s.label)];
  if (detectedServices.length === 0) labels.push("ci");

  title = `[${prefix}-${seq}] integration test failure (commit: ${shortSha})`;

  const logSections = [];
  for (const { name } of detectedServices) {
    const logPath = `/tmp/service-logs/${name}.log`;
    const logs = fs.existsSync(logPath) ? fs.readFileSync(logPath, "utf8") : "no logs captured";
    logSections.push(`### ${name}\n\`\`\`\n${logs}\n\`\`\``);
  }

  const closeInstructions = isStack
    ? [
        "## To close this issue",
        "This issue covers multiple failing services. Run targeted-test.yml for each service separately.",
        "Once all services pass, close this issue manually.",
        "",
        "For each failing service:",
        "1. Fix the service",
        "2. Go to **Actions → targeted-test.yml → Run workflow**",
        "3. Set **Service** to the affected service",
        "4. Set **Issue number** to the issue number shown in the title of this issue",
        "5. Verify the targeted test passes and the comment is posted",
        "6. Repeat for all remaining services",
        "7. Close this issue manually once all services are green",
      ]
    : [
        "## To close this issue",
        "1. Fix the failing service",
        "2. Go to **Actions → targeted-test.yml → Run workflow**",
        "3. Set **Service** to the affected service",
        "4. Set **Issue number** to the issue number shown in the title of this issue",
      ];

  body = [
    "## Integration test failure",
    "",
    `**Run:** ${runUrl}`,
    `**Commit:** ${shortSha}`,
    "",
    "## Test output (last 3000 chars)",
    "```",
    rawOutput.slice(-3000),
    "```",
    "",
    logSections.length > 0 ? "## Service logs\n\n" + logSections.join("\n\n") : "",
    "",
    ...closeInstructions,
  ].join("\n");
}

// Duplicate check - don't open a second issue for the same commit
const existing = await github.rest.issues.listForRepo({
  owner: context.repo.owner,
  repo: context.repo.repo,
  state: "open",
  labels: "test-failure",
  per_page: 100,
});

const duplicate = existing.data.find((i) => i.title.includes(shortSha));
if (duplicate) {
  console.log(`Duplicate suppressed - issue #${duplicate.number} already exists for ${shortSha}`);
  return;
}

await github.rest.issues.create({
  owner: context.repo.owner,
  repo: context.repo.repo,
  title,
  body,
  labels,
});
````

---

## Part 2 - Targeted Test Workflow

### File to Create: `.github/workflows/targeted-test.yml`

```yaml
name: CI - Targeted Test

on:
  workflow_dispatch:
    inputs:
      service:
        description: "Service to test"
        required: true
        type: choice
        options:
          - statporter
          - weather-app
          - prometheus
          - loki
          - grafana
          - alertmanager
          - demo-container
          - reverse-proxy
          - promtail
      issue_number:
        description: "Issue number to comment on or close"
        required: true
        type: string

jobs:
  targeted-test:
    runs-on: ubuntu-latest

    permissions:
      issues: write

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Create .env for CI
        working-directory: weather-app/docker-final
        run: |
          cp .env.example .env
          SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
          sed -i "s|change-me-generate-a-real-secret|$SECRET|g" .env

      - name: Validate .env
        working-directory: weather-app/docker-final
        run: |
          if grep -q "change-me-generate-a-real-secret" .env; then
            echo "ERROR: .env still contains placeholder secret"
            exit 1
          fi

      - name: Pull images
        working-directory: weather-app/docker-final
        run: docker compose pull

      - name: Start stack
        working-directory: weather-app/docker-final
        run: docker compose up -d

      - name: Wait for healthchecks
        # loki is distroless (no shell/wget) - no Docker healthcheck; polled separately
        # weather-app, reverse-proxy, and promtail also have no HEALTHCHECK
        run: |
          for service in prometheus grafana statporter alertmanager demo-container; do
            echo "Waiting for $service..."
            timeout 120 bash -c \
              "until [ \"\$(docker inspect \
              --format='{{.State.Health.Status}}' \
              $service 2>/dev/null)\" = 'healthy' ]; do sleep 3; done"
          done

      - name: Wait for Loki readiness
        run: |
          timeout 120 bash -c \
            "until docker exec prometheus wget -q --spider http://loki:3100/ready 2>/dev/null; do sleep 3; done"
          echo "loki is ready"
          sleep 5

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install test dependencies
        run: pip install -r weather-app/docker-final/requirements-dev.txt

      - name: Run targeted tests
        id: run-tests
        run: |
          set -o pipefail
          pytest weather-app/docker-final/tests/ -v --tb=short \
            -k "${{ inputs.service }}" 2>&1 | tee targeted-test-output.txt

      - name: Capture service logs on failure
        if: failure()
        run: |
          mkdir -p /tmp/service-logs
          for service in weather-app statporter prometheus grafana loki promtail alertmanager reverse-proxy demo-container; do
            docker logs $service --tail 50 2>&1 > /tmp/service-logs/${service}.log || echo "no logs available" > /tmp/service-logs/${service}.log
          done

      - name: Comment on issue on success
        if: success()
        uses: actions/github-script@v7
        with:
          script: |
            const core = require('@actions/core');
            const issueNumber = parseInt('${{ inputs.issue_number }}');
            if (isNaN(issueNumber) || issueNumber < 1) {
              core.setFailed(`Invalid issue number: '${{ inputs.issue_number }}'`);
              return;
            }

            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;

            const issue = await github.rest.issues.get({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: issueNumber,
            });

            const isStack = issue.data.title.startsWith('[STACK-');

            if (isStack) {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: issueNumber,
                body: `## Targeted test passed - \`${{ inputs.service }}\`\n\n**Run:** ${runUrl}\n\nThis is a multi-service issue. Verify all other failing services before closing manually.`,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: issueNumber,
                body: `## Targeted test passed - closing\n\n**Service:** \`${{ inputs.service }}\`\n**Run:** ${runUrl}`,
              });

              await github.rest.issues.update({
                owner: context.repo.owner,
                repo: context.repo.repo,
                issue_number: issueNumber,
                state: 'closed',
              });
            }

      - name: Comment on issue on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const core = require('@actions/core');
            const fs = require('fs');
            const issueNumber = parseInt('${{ inputs.issue_number }}');
            if (isNaN(issueNumber) || issueNumber < 1) {
              core.setFailed(`Invalid issue number: '${{ inputs.issue_number }}'`);
              return;
            }

            const output = fs.existsSync('targeted-test-output.txt')
              ? fs.readFileSync('targeted-test-output.txt', 'utf8').slice(-2000)
              : 'No output captured';
            const runUrl = `${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;

            const logPath = `/tmp/service-logs/${{ inputs.service }}.log`;
            const logs = fs.existsSync(logPath)
              ? fs.readFileSync(logPath, 'utf8')
              : 'no logs captured';

            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: issueNumber,
              body: `## Targeted test still failing\n\n**Service:** \`${{ inputs.service }}\`\n**Run:** ${runUrl}\n\n### Test output\n\`\`\`\n${output}\n\`\`\`\n\n### Service logs\n\`\`\`\n${logs}\n\`\`\``,
            });

      - name: Tear down stack
        if: always()
        working-directory: weather-app/docker-final
        run: docker compose down -v
```

---

## Part 3 - Required Labels

**Step 0: Create all labels in the repo before running any workflow.**

| Label                | Color     | Purpose                                                                              |
| -------------------- | --------- | ------------------------------------------------------------------------------------ |
| `test-failure`       | `#e11d48` | All test failures                                                                    |
| `ci`                 | `#6366f1` | CI infrastructure failures                                                           |
| `svc:weather-app`    | `#0075ca` | Weather app failures                                                                 |
| `svc:statporter`     | `#7c3aed` | Statporter failures                                                                  |
| `svc:prometheus`     | `#e4761b` | Prometheus failures                                                                  |
| `svc:grafana`        | `#f97316` | Grafana failures                                                                     |
| `svc:loki`           | `#0891b2` | Loki failures                                                                        |
| `svc:promtail`       | `#0e7490` | Promtail failures                                                                    |
| `svc:alertmanager`   | `#e4541a` | Alertmanager failures                                                                |
| `svc:nginx`          | `#0e8a16` | Nginx/reverse-proxy failures                                                         |
| `svc:demo-container` | `#cfd3d7` | Demo container failures                                                              |
| `severity:critical`  | `#b60205` | Reserved - stack won't start                                                         |
| `severity:high`      | `#d93f0b` | Reserved - service down                                                              |
| `severity:low`       | `#e4e669` | Reserved - non-blocking                                                              |
| `vendor-cve`         | `#e11d48` | CRITICAL CVEs in vendor images (auto-managed by image scan step)                     |
| `own-image-cve`      | `#b60205` | CRITICAL CVEs in burningstar4/ images - CI blocked (auto-managed by image scan step) |

The three `severity:*` labels are reserved for future auto-assignment and are not used by any workflow in this spec.

---

## Part 4 - Test Filter Convention

`targeted-test.yml` uses `-k "${{ inputs.service }}"` to filter pytest. Pytest matches this expression as a substring against the full test node ID (file::class::function[param]), so parametrized tests are filtered by their parameter values automatically.

**Current behavior with existing tests:**

- `-k "statporter"` matches `TestStatporterCollector` (class name) and any parametrized case with `statporter` in the ID
- `-k "weather-app"` matches `test_container_exists[weather-app]`, `test_container_is_running[weather-app]`, etc. - all parametrized cases for that container

**Convention for new test files:**

Class names must include the service name they test, and files must be named accordingly. This drives both the `-k` filter and the issue labeling - no special formatting in failure messages is required.

| Test target           | File name                | Class name                     | Label assigned       |
| --------------------- | ------------------------ | ------------------------------ | -------------------- |
| Flask routes          | `test_weather_app.py`    | `TestWeatherAppRoutes`         | `svc:weather-app`    |
| Playground auth       | `test_weather_app.py`    | `TestWeatherAppPlaygroundAuth` | `svc:weather-app`    |
| statporter exporter   | `test_statporter.py`     | `TestStatporterMetrics`        | `svc:statporter`     |
| nginx routing         | `test_nginx.py`          | `TestNginxRouting`             | `svc:nginx`          |
| demo-container stress | `test_demo_container.py` | `TestDemoContainerStress`      | `svc:demo-container` |

**How detection works for unit tests:**

Pass 2 lowercases all `FAILED` lines from pytest output and checks each service's `terms` array against them. A failing test in `test_weather_app.py::TestWeatherAppRoutes` produces a FAILED line containing `weather_app`, which matches the `weather-app` entry's term. No changes to failure message text are needed.

The only requirement is that file and class names follow the table above. A test that does not match any term still produces a structured `[CI-NNNN]` issue - it is never silently dropped.

---

## Testing Checklist

- [ ] **Step 0: Verify all labels in Part 3 exist in the repo**
- [ ] Push a change that causes a known single-service test to fail - verify issue title is `[PREFIX-NNNN]` format
- [ ] Verify correct `svc:` label applied for single service failure
- [ ] Push a change that causes multiple services to fail - verify `STACK` prefix and multiple `svc:` labels
- [ ] Verify `[CI-NNNN]` title and `ci` label when test output is empty
- [ ] Verify per-service log sections appear in issue body
- [ ] Verify close/investigate instructions appear in issue body (single-service and STACK variants differ)
- [ ] Trigger `targeted-test.yml` for a passing single-service issue - verify issue auto-closes with comment
- [ ] Trigger `targeted-test.yml` for a passing STACK issue - verify comment is posted but issue stays open
- [ ] Trigger `targeted-test.yml` for a failing service - verify failure comment includes test output and service logs, issue stays open
- [ ] Introduce a failing unit test in a file following the Part 4 naming convention - verify it receives a per-service label (not `[CI-NNNN]`)
- [ ] Verify duplicate check - same commit SHA doesn't open two issues
- [ ] Verify `Fixes #N` in commit message also closes the issue as an alternative path
- [ ] `pre-commit run --all-files` passes on all new and modified files

---

## What This Does Not Cover

- **Automatic targeted test trigger on push** - requires a PAT with `workflow` scope; deferred
- **Severity label auto-assignment** - requires tests to emit severity signals; labels exist in repo as placeholders
- **STACK issue auto-close** - multi-service resolution tracking is out of scope; STACK issues are closed manually after all services verified
- **Cross-issue deduplication beyond same-commit SHA** - the same service failing across multiple commits will open multiple issues; deduplication is by SHA only
