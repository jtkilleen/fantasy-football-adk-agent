# Fantasy Football Personal Agent

## General
The fantasy football personal agent is responsible for answering user queries regarding their fantasy football team. The agent must be responsible for handling a multitude of requests such as knowing which players are available to pick up, if the user should pick up a player, how their team compares to their current opponent, and trade suggestions with other players in the league.

The agent must be able to handle analytical questions such as "How is my quarterback trending vs this time last year?" or "Please analyze my bench and see who I should start or drop". The agent should be able to perform high-level searches on players and teams to inform the user on insights.

The agent uses a self-contained **Synthetic Fantasy Football Data Engine** (seeded multi-season weekly player stats, league rosters, weekly opponent matchups, waiver wire pool, and player/team scouting insights) to showcase agentic architecture without requiring external third-party fantasy APIs.

## Architecture Info
* This should be created as a git repo and it will eventually be public.
* This agent should be usable as a demo/reference architecture and won't be totally productionized.
* This project should be created in Python using the [Google ADK](https://github.com/google/adk-python). It should create a Python `uv` environment specially made for this project.
* This project uses Google Cloud to deploy resources and uses Terraform as Infrastructure as Code (IaC) for handling the deployment.
* This project will use Gemini for all LLM calls.
