# asana_public

These are some scripts I've built to do things that Asana cannot do natively. Most will require an API token, and the ability to put the secret keys in a .env file.

I used VScode to create these, and have no idea is they will work using anything else


# Asana Projects Exporter

This Flask application exports projects (and associated tasks, subtasks, stories, and attachments) from Asana.

## Features

- Securely loads API tokens from environment variables
- Exports project data in JSON format
- Downloads task attachments to a project-wide folder
- Processes projects concurrently using threads

## Getting Started

### Prerequisites

- Python 3.7+
- A valid [Asana API token](https://asana.com/developers) and workspace GID


