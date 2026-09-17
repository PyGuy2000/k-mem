# A machine that has never seen the author's repos: python3, git, node, Claude Code.
#
#   docker build -t kmem-fresh -f docker/Dockerfile .
#   docker run --rm kmem-fresh                       # installs from GitHub
#   docker run --rm -v "$PWD":/src kmem-fresh /src   # installs from this checkout
#
# The script prints PASS/FAIL per step. Opening a live session (the gate
# refusing an unread edit through Claude itself) needs an API key and is
# graded by hand; everything the hooks do is exercised here through the
# same launchers Claude Code runs.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && pip install "mcp<2" pytest \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -d /opt/tester tester
USER tester
WORKDIR /opt/tester
# No git URL rewriting here on purpose. An earlier version rewrote github SSH
# URLs to https, which hid a real defect: the marketplace listed DevFlow as a
# github source, that clones over SSH, and every machine with no GitHub SSH
# key could not install it. The image must fail the way a stranger's machine
# fails, so the marketplace uses an https url source instead.
COPY --chown=tester scripts/fresh_machine_test.sh /opt/tester/fresh_machine_test.sh
ENTRYPOINT ["bash", "/opt/tester/fresh_machine_test.sh"]
