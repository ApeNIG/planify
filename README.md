# Planify

Multi-agent planning orchestrator for software projects.

## Installation

```bash
poetry install
```

## Usage

```bash
# Set API keys
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# Run planning
planify "Add email notifications" --repo /path/to/project
```

## Features

- **Architect** (OpenAI): Drafts comprehensive implementation plans
- **Critic** (Claude): Challenges plans to find gaps and risks
- **Integrator**: Merges feedback into final actionable plan
- **Human-in-the-loop**: Review and provide feedback after each phase
- **Session persistence**: Resume planning sessions from JSON files
- **Secret scrubbing**: Automatically redacts API keys and secrets
